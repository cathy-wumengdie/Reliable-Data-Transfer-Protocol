# Packet definition for CS 456/656 Assignment 2
import struct


HEADER_FORMAT = "!IIIII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_DATA_LENGTH = 500


class Packet:
    """
    Constructs a Packet either by specifying fields:
        Packet(type, seqnum, length, ecn, ce_count, data)
    or by providing an encoded packet:
        Packet(encoded_packet)
    """

    def __init__(self, *args):
        if len(args) == 1:
            self._decode_from_bytes(args[0])
            return

        if len(args) != 6:
            raise RuntimeError("Expected 6 arguments: type, seqnum, length, ecn, ce_count, data")

        typ, seqnum, length, ecn, ce_count, data = args

        self.typ = int(typ)
        self.seqnum = int(seqnum)
        self.length = int(length)
        self.ecn = int(ecn)
        self.ce_count = int(ce_count)
        self.data = data

        if not isinstance(self.data, str):
            raise RuntimeError("Packet data must be a string")
        if self.length < 0 or self.length > MAX_DATA_LENGTH:
            raise RuntimeError("Packet length should be in range [0, {}]".format(MAX_DATA_LENGTH))

        encoded_data = self.data.encode("ASCII")
        if len(encoded_data) != self.length:
            raise RuntimeError("Packet length does not match encoded data length")

    def _decode_from_bytes(self, encoded_packet):
        if not isinstance(encoded_packet, bytes):
            raise RuntimeError("Expected bytes when constructing from encoded packet")
        if len(encoded_packet) < HEADER_SIZE:
            raise RuntimeError("Encoded packet is shorter than header size")

        self.typ, self.seqnum, self.length, self.ecn, self.ce_count = struct.unpack(
            HEADER_FORMAT, encoded_packet[:HEADER_SIZE]
        )

        if self.length > MAX_DATA_LENGTH:
            raise RuntimeError("Decoded packet length exceeds {}".format(MAX_DATA_LENGTH))

        expected_size = HEADER_SIZE + self.length
        if len(encoded_packet) < expected_size:
            raise RuntimeError("Encoded packet does not contain full payload")

        payload = encoded_packet[HEADER_SIZE:expected_size]
        self.data = payload.decode("ASCII")

    def encode(self):
        encoded_data = self.data.encode("ASCII")
        if len(encoded_data) != self.length:
            raise RuntimeError("Packet length does not match encoded data length")

        return struct.pack(
            "{}{}s".format(HEADER_FORMAT, self.length),
            self.typ,
            self.seqnum,
            self.length,
            self.ecn,
            self.ce_count,
            encoded_data,
        )

    def decode(self):
        return int(self.typ), int(self.seqnum), int(self.length), int(self.ecn), int(self.ce_count), self.data

    def __repr__(self):
        ret = "Type={}\n".format(self.typ)
        ret += "Seqnum={}\n".format(self.seqnum)
        ret += "Length={}\n".format(self.length)
        ret += "ECN={}\n".format(self.ecn)
        ret += "CE_Count={}\n".format(self.ce_count)
        ret += "Data={}".format(self.data)
        return ret


if __name__ == "__main__":
    testmsg = "testmsg"
    packet1 = Packet(1, 1, len(testmsg), 0, 0, testmsg)
    print(packet1)
    packet1_enc = packet1.encode()
    print(packet1_enc)
    packet2 = Packet(packet1_enc)
    print(packet2)
