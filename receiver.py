import sys
from socket import *
from packet import Packet

CHUNK_SIZE = 1024
ACK = 0
DATA = 1
EOT = 2

def mod32(x):
    return x % 32

# Computes the modular distance between a sequence number and the expected sequence
def seq_distance(seq, expected):
    return (seq - expected + 32) % 32

def send_packet(sock, emulator_host, emulator_ack_port, typ, seqnum, ce_total):
    ack_pkt = Packet(typ, seqnum, 0, 0, ce_total, "")
    sock.sendto(ack_pkt.encode(), (emulator_host, emulator_ack_port))

def main():
    # Check correct number of command line arguments
    if len(sys.argv) != 5:
        sys.exit(1)

    # Parse command line arguments
    emulator_host = sys.argv[1]          # hostname of network emulator
    emulator_ack_port = int(sys.argv[2]) # port emulator listens for ACKs
    receiver_port = int(sys.argv[3])     # port receiver listens for data packets
    output_file = sys.argv[4]            # file where received data will be written

    sock = socket(AF_INET, SOCK_DGRAM)
    # Bind socket to receiver port to receive packets from emulator
    sock.bind(("", receiver_port))

    # Receiver state variables
    expected_seqnum = 0        # next sequence number expected
    last_in_order_seqnum = 31  # last correctly received packet sequence number
    ce_total = 0               # cumulative ECN-mark count for in-order packets
    buffer = {}                # stores out-of-order packets

    outfile = open(output_file, "w")
    arrival_log = open("arrival.log", "w")

    while True:
        # Receive UDP packet from emulator
        packet_bytes, addr = sock.recvfrom(CHUNK_SIZE)

        # Decode packet
        pkt = Packet(packet_bytes)
        
        # Log packet arrival
        if pkt.typ == EOT:
            arrival_log.write("EOT\n")
        else:
            arrival_log.write(f"{pkt.seqnum} {pkt.ecn}\n")
        arrival_log.flush()
        
        # Compute distance between received packet sequence number and expected sequence number
        distance = seq_distance(pkt.seqnum, expected_seqnum)

        # Case 1: packet sequence number matches expected sequence number
        if distance == 0:
            # If packet is End Of Transmission (EOT)
            if pkt.typ == 2:
                # Send EOT back to sender to confirm termination
                send_packet(sock, emulator_host, emulator_ack_port, EOT, pkt.seqnum, ce_total)
                break

            # If packet is a DATA packet with expected sequence number
            elif pkt.typ == 1:
                # Write packet payload to output file
                outfile.write(pkt.data)
                outfile.flush()

                # If ECN mark is set, increment cumulative counter
                if pkt.ecn == 1:
                    ce_total += 1

                # Update last correctly received sequence number
                last_in_order_seqnum = pkt.seqnum

                # Move expected sequence forward 
                expected_seqnum = mod32(expected_seqnum + 1)
                
                # Release buffered packets if next ones exist
                while expected_seqnum in buffer:
                    buffered_pkt = buffer.pop(expected_seqnum)
                    
                    # Write buffered packet data to output file
                    outfile.write(buffered_pkt.data)
                    outfile.flush()

                    if buffered_pkt.ecn == 1:
                        ce_total += 1

                    # Update last correctly received sequence number and expected sequence number after releasing buffered packets
                    last_in_order_seqnum = buffered_pkt.seqnum
                    expected_seqnum = mod32(expected_seqnum + 1)
                    
                send_packet(sock, emulator_host, emulator_ack_port, ACK, last_in_order_seqnum, ce_total)

        # Case 2: packet is within receiver window
        elif pkt.typ == DATA and 1 <= distance <= 10:
           # store if not already buffered
            if pkt.seqnum not in buffer:
                buffer[pkt.seqnum] = pkt
                
            send_packet(sock, emulator_host, emulator_ack_port, ACK, last_in_order_seqnum, ce_total)
        
        # Case 3: packet is outside receiver window, ignore and resend ACK for last in-order packet
        else:
            send_packet(sock, emulator_host, emulator_ack_port, ACK, last_in_order_seqnum, ce_total)


    # Close output file and socket when finished
    outfile.close()
    arrival_log.close()
    sock.close()


if __name__ == "__main__":
    main()