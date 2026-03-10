import sys
import time
import math
import select
from socket import *
from packet import Packet

ACK = 0
DATA = 1
EOT = 2
MAX_PAYLOAD = 500
CHUNK_SIZE = 1024
TIMEOUT = 0.3
RTT_INTERVAL = 0.1
G = 0.0625

def mod32(x):
    return x % 32

# Compute sender window size N from congestion window cwnd
def compute_N(cwnd):
    return max(1, min(10, math.floor(cwnd)))

# Read the input file and split it into chunks of size <= 500 bytes
def read_chunks(filename):
    with open(filename, "r") as f:
        data = f.read()
    return [data[i:i + MAX_PAYLOAD] for i in range(0, len(data), MAX_PAYLOAD)]

# Log packet transmissions
def log_seqnum(seqnum_log, t, seqnum):
    seqnum_log.write(f"t={t} {seqnum}\n")
    seqnum_log.flush()

# Log received ACKs
def log_ack(ack_log, t, seqnum, ce_count):
    ack_log.write(f"t={t} {seqnum} {ce_count}\n")
    ack_log.flush()

# Log window size changes
def log_N(n_log, t, N):
    n_log.write(f"t={t} {N}\n")
    n_log.flush()
    
# Advances the base index based on the ACKed sequence number
# If the ACK corresponds to a packet currently in the window, advance base cumulatively. Otherwise ignore it.
def advance_base(base, next_pkt, ack_seqnum):
    probe = base
    while probe < next_pkt and mod32(probe) != ack_seqnum:
        probe += 1

    if probe < next_pkt and mod32(probe) == ack_seqnum:
        return probe + 1   # cumulative ACK covers up to this packet
    return base            # old/duplicate ACK

# Send a data packet and log the transmission
def send_data_packet(sock, emulator_host, emulator_data_port, chunks, abs_index, seqnum_log, t):
    chunk = chunks[abs_index]
    seqnum = mod32(abs_index)
    pkt = Packet(DATA, seqnum, len(chunk), 0, 0, chunk)
    sock.sendto(pkt.encode(), (emulator_host, emulator_data_port))
    log_seqnum(seqnum_log, t, seqnum)

def main():
    if len(sys.argv) != 5:
        sys.exit(1)

    emulator_host = sys.argv[1]             # hostname of network emulator
    emulator_data_port = int(sys.argv[2])   # port emulator listens for data packets
    sender_port = int(sys.argv[3])          # port sender listens for ACKs and EOT from emulator
    input_file = sys.argv[4]                # file containing data to send

    # Read input file and split into chunks
    chunks = read_chunks(input_file)
    total = len(chunks)

    # Create UDP socket and bind to sender port
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(("", sender_port))
    
    seqnum_log = open("seqnum.log", "w")
    ack_log = open("ack.log", "w")
    n_log = open("N.log", "w")

    # Sender sliding window state
    base = 0            # oldest unacknowledged packet index
    next_pkt = 0        # next unsent packet index
    event_time = 0      # timestamp 
    
    # Congestion control variables
    cwnd = 1.0          # congestion window size
    N = compute_N(cwnd) # window size based on cwnd
    
    # ECN state variables
    alpha = 0.0         # congestion level estimate
    prev_ce_count = 0   # cumulative ECN count from last ACK that advanced base
    acked_in_rtt = 0    # number of newly acknowledged packets in this RTT window
    marked_in_rtt = 0   # number of newly acknowledged ECN-marked packets in this RTT window
    
    # Timer deadlines
    rtt_deadline = time.monotonic() + RTT_INTERVAL  # next time to apply ECN window reduction
    retransmit_deadline = None                      # timeout for oldest unacked packet
    
    # t = 0 for initialization
    log_N(n_log, event_time, N)
    
    while base < total:
        # Send as many new packets as window allows
        while next_pkt < total and next_pkt < base + N:
            event_time += 1
            send_data_packet(sock, emulator_host, emulator_data_port, chunks, next_pkt, seqnum_log, event_time)
            next_pkt += 1
        
        # Start retransmission timer if there are outstanding packets
        if base < next_pkt and retransmit_deadline is None:
            retransmit_deadline = time.monotonic() + TIMEOUT

        # Determine how long to wait for events
        now = time.monotonic()
        time_until_rtt = max(0, rtt_deadline - now)

        if retransmit_deadline is None:
            wait_time = time_until_rtt
        else:
            time_until_retx = max(0, retransmit_deadline - now)
            wait_time = min(time_until_rtt, time_until_retx)

        # Wait for incoming ACK or timer expiration
        ready, _, _ = select.select([sock], [], [], wait_time)

        now = time.monotonic()
        # Case 1: ACK received
        if ready:
            packet_bytes, addr = sock.recvfrom(CHUNK_SIZE)
            ack_pkt = Packet(packet_bytes)

            if ack_pkt.typ == ACK:
                event_time += 1
                log_ack(ack_log, event_time, ack_pkt.seqnum, ack_pkt.ce_count)

                old_base = base
                base = advance_base(base, next_pkt, ack_pkt.seqnum)

                # New packets were cumulatively acknowledged
                if base > old_base:
                    advance = base - old_base
                    ce_delta = ack_pkt.ce_count - prev_ce_count

                    acked_in_rtt += advance
                    marked_in_rtt += ce_delta
                    prev_ce_count = ack_pkt.ce_count

                    old_N = N
                    cwnd = cwnd + 1.0 / cwnd
                    N = compute_N(cwnd)

                    if N != old_N:
                        log_N(n_log, event_time, N)

                    # Restart retransmission timer if there are still unacked packets
                    if base < next_pkt:
                        retransmit_deadline = time.monotonic() + TIMEOUT
                    else:
                        retransmit_deadline = None

        # Case 2: either RTT tick or retransmission timeout happened
        else:
            now = time.monotonic()

            # Periodic ECN update
            while now >= rtt_deadline:
                if acked_in_rtt > 0:
                    F = marked_in_rtt / acked_in_rtt
                    alpha = (1 - G) * alpha + G * F

                    old_N = N
                    cwnd = cwnd * (1 - alpha / 2)
                    N = compute_N(cwnd)

                    if N != old_N:
                        log_N(n_log, event_time, N)

                acked_in_rtt = 0
                marked_in_rtt = 0
                rtt_deadline += RTT_INTERVAL

            # Retransmission timeout
            if retransmit_deadline is not None and now >= retransmit_deadline:
                event_time += 1

                old_N = N
                cwnd = 1.0
                N = compute_N(cwnd)

                if N != old_N:
                    log_N(n_log, event_time, N)

                # Retransmit oldest unacknowledged packet
                send_data_packet(sock, emulator_host, emulator_data_port, chunks, base, seqnum_log, event_time)
                retransmit_deadline = time.monotonic() + TIMEOUT
                
    # Send EOT after all data packets are acknowledged
    event_time += 1
    eot_seqnum = mod32(next_pkt)
    eot_pkt = Packet(EOT, eot_seqnum, 0, 0, 0, "")
    sock.sendto(eot_pkt.encode(), (emulator_host, emulator_data_port))
    seqnum_log.write(f"t={event_time} EOT\n")
    seqnum_log.flush()

    # Wait for EOT response
    while True:
        ready, _, _ = select.select([sock], [], [], TIMEOUT)

        if ready:
            packet_bytes, _ = sock.recvfrom(CHUNK_SIZE)
            pkt = Packet(packet_bytes)
            if pkt.typ == EOT:
                event_time += 1
                ack_log.write(f"t={event_time} EOT {pkt.ce_count}\n")
                ack_log.flush()
                break
        else:
            # Retransmit EOT if no response received within timeout
            event_time += 1
            sock.sendto(eot_pkt.encode(), (emulator_host, emulator_data_port))
            seqnum_log.write(f"t={event_time} EOT\n")
            seqnum_log.flush()

    seqnum_log.close()
    ack_log.close()
    n_log.close()
    sock.close()

if __name__ == "__main__":
    main()