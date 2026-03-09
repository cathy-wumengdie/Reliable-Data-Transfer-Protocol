# Overview

This project implements a reliable data transfer protocol over UDP using a sliding window mechanism with congestion control and ECN (Explicit Congestion Notification). The project contains the following files:

- `sender.py` — sends packets reliably to the receiver through the network emulator
- `receiver.py` — receives packets, buffers out-of-order packets, writes data in order, and sends ACKs
- `network_emulator.py` — simulates packet loss, delay, and ECN marking
- `packet.py` — packet encoding and decoding support
- `Sample_input.txt` — sample input file for testing

The sender adjusts its congestion window using additive increase and ECN-based congestion control.

### Programming Language

- Python 3

Ensure Python 3 is installed before running the program: `python3 --version`

# Testing Instructions

The program can be executed on separate CS student environment machines.

Start the programs in the following order:

## 1. Run Network Emulator

```python3 network_emulator.py <emulator port receiving packets from sender> <receiver_host> <receiver listening port> <emulator port receiving ACKs>  <sender_host> <sender listening port> <packet discard probability> <target packet rate (range 10-100 packets per sec)> <verbose-mode (set to 1)>```

Example: 
- `python3 network_emulator.py 9991 ubuntu2404-004.student.cs.uwaterloo.ca 9994 9993 ubuntu2404-006.student.cs.uwaterloo.ca 9992 0.05 10 1`


## 2. Run Receiver

```python3 receiver.py <emulator_host> <emulator port receiving ACKs> <receiver listening port> <output_file>```

Example:
- `python3 receiver.py ubuntu2404-002.student.cs.uwaterloo.ca 9993 9994 output.txt`

## 3. Run Sender

```python3 sender.py <emulator_host> <emulator port receiving packets from sender> <sender listening port> <input_file>```

Example:
- `python3 sender.py ubuntu2404-002.student.cs.uwaterloo.ca 9991 9992 Sample_input.txt`

### Testing Environment

The program was built and tested on the University of Waterloo CS student Linux machines:

- `<emulator_host>: ubuntu2404-002.student.cs.uwaterloo.ca`

- `<receiver_host>: ubuntu2404-004.student.cs.uwaterloo.ca`

- `<sender_host>: ubuntu2404-006.student.cs.uwaterloo.ca`

### Output Files
The following log files are generated:
- seqnum.log - Sequence numbers of packets sent
- ack.log - ACK packets received
- N.log - Sender window size updates
- arrival.log - Packets received by receiver
