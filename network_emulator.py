from packet import Packet
import argparse
import random
import socket
import threading
import time
from queue import Queue


DEFAULT_MAX_DELAY_MS = 100
RATE_WINDOW_MS = 100


forward_recv_port = None
backward_recv_port = None
receiver_addr = None
receiver_recv_port = None
sender_addr = None
sender_recv_port = None
prob_discard = None
target_packet_rate = None
verbose = False


data_buff = Queue()
ack_buff = Queue()

ecn_lock = threading.Lock()
data_packet_count = 0
ecn_mark_probability = 0.0


def randomTrue(probability):
    return random.random() < probability


def delayThread(delay_ms):
    if verbose:
        print("Packet delayed by {} milliseconds".format(delay_ms))
    time.sleep(delay_ms / 1000.0)


def send_packet(packet_bytes, dst_addr, dst_port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet_bytes, (dst_addr, dst_port))


def forward_data_packet_with_ecn(recvd_packet):
    typ, seqnum, length, _, _, data = recvd_packet.decode()
    with ecn_lock:
        mark_probability = ecn_mark_probability
    ecn_mark = 1 if randomTrue(mark_probability) else 0
    return Packet(typ, seqnum, length, ecn_mark, 0, data)


def processPacket(packet, fromSender):
    global data_packet_count

    if not isinstance(packet, bytes):
        raise RuntimeError("processPacket can only process a packet encoded as bytes")

    recvd_packet = Packet(packet)
    typ, seqnum, length, ecn, ce_count, data = recvd_packet.decode()

    if verbose:
        print(
            "Packet being processed: Type={}, seqnum={}, length={}, ecn={}, ce_count={}, data={}".format(
                typ, seqnum, length, ecn, ce_count, data
            )
        )

    if fromSender and typ == 1:
        with ecn_lock:
            data_packet_count += 1

    if typ == 2:
        if fromSender:
            while not data_buff.empty():
                delayThread(DEFAULT_MAX_DELAY_MS)
            if verbose:
                print(
                    "Sending packet: Type={}, seqnum={}, length={}, ecn={}, ce_count={}, data={}".format(
                        typ, seqnum, length, ecn, ce_count, data
                    )
                )
            send_packet(packet, receiver_addr, receiver_recv_port)
        else:
            while not ack_buff.empty():
                delayThread(DEFAULT_MAX_DELAY_MS)
            if verbose:
                print(
                    "Sending packet: Type={}, seqnum={}, length={}, ecn={}, ce_count={}, data={}".format(
                        typ, seqnum, length, ecn, ce_count, data
                    )
                )
            send_packet(packet, sender_addr, sender_recv_port)
        return

    if randomTrue(prob_discard):
        if verbose:
            print(
                "Dropped packet: Type={}, seqnum={}, length={}, ecn={}, ce_count={}, data={}".format(
                    typ, seqnum, length, ecn, ce_count, data
                )
            )
        return

    if fromSender:
        if typ == 0:
            raise RuntimeError("Received an ACK from the sender")
        data_buff.put(packet)
        packet_to_send = forward_data_packet_with_ecn(recvd_packet) if typ == 1 else recvd_packet
    else:
        if typ == 1:
            raise RuntimeError("Received data from the receiver")
        ack_buff.put(packet)
        packet_to_send = recvd_packet

    delay = random.randint(0, DEFAULT_MAX_DELAY_MS)
    delayThread(delay)

    if fromSender:
        data_buff.get(block=False)
        dst_addr, dst_port = receiver_addr, receiver_recv_port
    else:
        ack_buff.get(block=False)
        dst_addr, dst_port = sender_addr, sender_recv_port

    send_bytes = packet_to_send.encode()

    if verbose:
        p_typ, p_seq, p_len, p_ecn, p_ce_count, p_data = packet_to_send.decode()
        print(
            "Sending packet: Type={}, seqnum={}, length={}, ecn={}, ce_count={}, data={}".format(
                p_typ, p_seq, p_len, p_ecn, p_ce_count, p_data
            )
        )

    send_packet(send_bytes, dst_addr, dst_port)


def forwardFlow():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", forward_recv_port))
    while True:
        packet = sock.recv(1024)
        if verbose:
            print("Received a packet from sender")
        new_thread = threading.Thread(target=processPacket, args=(packet, True))
        new_thread.start()


def backwardFlow():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", backward_recv_port))
    while True:
        packet = sock.recv(1024)
        if verbose:
            print("Received a packet from receiver")
        new_thread = threading.Thread(target=processPacket, args=(packet, False))
        new_thread.start()


def ecnRateLoop():
    global data_packet_count
    global ecn_mark_probability

    while True:
        rate_window_seconds = RATE_WINDOW_MS / 1000.0
        time.sleep(rate_window_seconds)
        with ecn_lock:
            count = data_packet_count
            data_packet_count = 0
            current_rate = count / rate_window_seconds
            if current_rate <= target_packet_rate:
                ecn_mark_probability = 0.0
            else:
                ecn_mark_probability = min(1.0, (current_rate - target_packet_rate) / target_packet_rate)
            new_probability = ecn_mark_probability

        if verbose:
            print(
                "ECN update: Rcur={:.2f} pps, Rt={:.2f} pps, pecn={:.4f}".format(
                    current_rate, target_packet_rate, new_probability
                )
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "forward_recv_port",
        metavar="<Forward receiving port>",
        type=int,
        help="emulator's receiving UDP port number in the forward (sender) direction",
    )
    parser.add_argument("receiver_addr", metavar="<Receiver's network address>")
    parser.add_argument("receiver_recv_port", metavar="<Receiver's receiving UDP port number>", type=int)
    parser.add_argument(
        "backward_recv_port",
        metavar="<Backward receiving port>",
        type=int,
        help="emulator's receiving UDP port number in the backward (receiver) direction",
    )
    parser.add_argument("sender_addr", metavar="<Sender's network address>")
    parser.add_argument("sender_recv_port", metavar="<Sender's receiving UDP port number>", type=int)
    parser.add_argument("drop_probability", metavar="<packet discard probability>", type=float)
    parser.add_argument(
        "target_packet_rate",
        metavar="<Target packet rate 10-100 pps>",
        type=float,
        help="target packet rate to prevent congestion, in packets/sec",
    )
    parser.add_argument("verbose_mode", metavar="<verbose-mode>", nargs="?", default=0, type=int)
    args = parser.parse_args()

    forward_recv_port = args.forward_recv_port
    backward_recv_port = args.backward_recv_port
    receiver_addr = args.receiver_addr
    receiver_recv_port = args.receiver_recv_port
    sender_addr = args.sender_addr
    sender_recv_port = args.sender_recv_port
    prob_discard = args.drop_probability
    target_packet_rate = args.target_packet_rate
    verbose = (args.verbose_mode == 1)

    if prob_discard < 0.0 or prob_discard > 1.0:
        raise RuntimeError("Packet discard probability should be between 0 and 1")
    if target_packet_rate < 10.0 or target_packet_rate > 100.0:
        raise RuntimeError("Target packet rate should be in range [10, 100] packets/sec")

    ecn_thread = threading.Thread(target=ecnRateLoop, daemon=True)
    forward_thread = threading.Thread(target=forwardFlow)
    backward_thread = threading.Thread(target=backwardFlow)

    if verbose:
        print("Starting network emulator and waiting for packets...")

    ecn_thread.start()
    forward_thread.start()
    backward_thread.start()

    while not forward_thread.is_alive():
        pass
    forward_thread.join()

    while not backward_thread.is_alive():
        pass
    backward_thread.join()
