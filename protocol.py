import struct
from typing import Tuple

# === Constans ===
MAGIC_COOKIE = 0xabcddcba

MTYPE_OFFER = 0x2 # UDP
MTYPE_REQUEST = 0x3 # TCP
MTYPE_PAYLOAD = 0x4 # TCP both sides

GAME_RESULT_NOTOVER = 0x0
GAME_RESULT_TIE = 0x1
GAME_RESULT_LOSS = 0x2
GAME_RESULT_WIN = 0x3

NAME_LEN = 32 # fixed length name field (bytes)

# === Struct Formats === I=4bytes, B=1byte, H=2bytes, Xs=Xbytes
OFFER_FMT = f"!I B H {NAME_LEN}s" # cookie(4) + type(1) + port(2) + name(32) = 39 bytes
REQUEST_FMT = f"!I B B {NAME_LEN}s" # cookie(4) + type(1) + rounds(1) + name(32) = 38 bytes

CLIENT_PAYLOAD_FMT = "!I B 5s" # cookie(4) + type(1) + decision(5) = 10 bytes
SERVER_PAYLOAD_FMT = "!I B B H B" # cookie(4) + type(1) + result(1) + rank(2) + suit(1) = 9 bytes

OFFER_SIZE = struct.calcsize(OFFER_FMT)
REQUEST_SIZE = struct.calcsize(REQUEST_FMT)
CLIENT_PAYLOAD_SIZE = struct.calcsize(CLIENT_PAYLOAD_FMT)
SERVER_PAYLOAD_SIZE = struct.calcsize(SERVER_PAYLOAD_FMT)

# === Fixed-Length Name Helper ===
def pack_name(name):
    """
    Converts a string name into exactly 32 bytes
    
    - Encodes the string to bytes (UTF-8)
    - Trimmed if longer than 32 bytes
    - Pads with null bytes (\\x00) if shorter
    
    This is used when sending names over the network,
    because the protocol requires a fixed length field
    """
    bytes_name = name.encode("utf-8") # name as bytes
    bytes_name = bytes_name[:NAME_LEN] # max of 32 bytes
    bytes_name += b"\x00" * (NAME_LEN - len(bytes_name)) # pad with zeros
    return bytes_name

def unpack_name(bytes_name):
    """
    Converts a 32-byte name field back into a string
    
    - Removes padding (null bytes \\x00)
    - Decodes bytes back to string
    
    This is used when receiving names from the network
    """
    bytes_name = bytes_name.split(b"\x00")[0] # remove padding
    return bytes_name.decode("utf-8") # bytes to string

def pack_offer(tcp_port, server_name):
    """
    Builds an OFFER message according to the protocol given in the assignment

    The OFFER message is sent from the server to clients over UDP
    It contains:
    - Magic cookie (4 bytes)
    - Message type = OFFER (1 byte)
    - TCP port of the server (2 bytes)
    - Server name (32 bytes, fixed length)

    Parameters:
    tcp_port     -- the TCP port that clients should connect to
    server_name  -- the server's team name (string)

    Returns:
    A bytes object of length 39, ready to be sent over UDP
    """
    return struct.pack(OFFER_FMT, MAGIC_COOKIE, MTYPE_OFFER, tcp_port, pack_name(server_name))

def unpack_offer(data):
    """
    Parses an OFFER message received over UDP

    Expects a bytes object that follows the OFFER format:
    - Magic cookie (4 bytes)
    - Message type (1 byte)
    - TCP port (2 bytes)
    - Server name (32 bytes)

    Parameters:
    data -- bytes received from the network (should be 39 bytes)

    Returns:
    A tuple:
    (cookie, message_type, tcp_port, server_name_str)

    server_name_str is returned as a regular string
    """
    cookie, message_type, tcp_port, server_name_str = struct.unpack(OFFER_FMT, data)
    return cookie, message_type, tcp_port, unpack_name(server_name_str)

def pack_request(rounds, client_name): 
    """
    Builds a REQUEST message according to the protocol in the assignment

    The REQUEST message is sent from the client to the server over TCP
    It contains:
    - Magic cookie (4 bytes)
    - Message type = REQUEST (1 byte)
    - Number of rounds (1 byte)
    - Client team name (32 bytes, fixed-length)

    Parameters:
    rounds       -- how many rounds the client wants to play (0-255)
    client_name  -- the client's team name (string)

    Returns:
    A bytes object of length 38, ready to be sent over TCP.
    """
    if not (0 <= rounds <= 255):
        raise ValueError('rounds must fit in 1 byte (0-255)')
    return struct.pack(REQUEST_FMT, MAGIC_COOKIE, MTYPE_REQUEST, rounds, pack_name(client_name))

def unpack_request(data):
    """
    Parses a REQUEST message received over TCP.

    Expects a bytes object that follows the REQUEST format:
    - Magic cookie (4 bytes)
    - Message type = REQUEST (1 byte)
    - Number of rounds (1 byte)
    - Client team name (32 bytes)

    Parameters:
    data -- bytes received from the network (should be 38 bytes)

    Returns:
    A tuple:
    (cookie, message_type, rounds, client_name)

    client_name_str is returned as a regular string
    """
    cookie, message_type, rounds, client_name_str = struct.unpack(REQUEST_FMT, data)
    return cookie, message_type, rounds, unpack_name(client_name_str)

def pack_client_payload(decision):
    """
    Builds a PAYLOAD message sent from client to server

    The payload contains:
    - Magic cookie (4 bytes)
    - Message type = PAYLOAD (1 byte)
    - Player decision (5 bytes): "Hittt" or "Stand"

    Parameters:
    decision -- string, must be exactly "Hittt" or "Stand"

    Returns:
    A bytes object - length 10
    """
    if decision not in ("Hittt", "Stand"):
        raise ValueError('decision must be "Hittt" or "Stand"')
    return struct.pack(CLIENT_PAYLOAD_FMT, MAGIC_COOKIE, MTYPE_PAYLOAD, decision.encode("ascii"))

def unpack_client_payload(data):
    """
    Parses a PAYLOAD message received from the client

    Returns:
    (cookie, message_type, decision)
    """
    cookie, message_type, decision_str = struct.unpack(CLIENT_PAYLOAD_FMT, data)
    return cookie, message_type, decision_str.decode("ascii")

def pack_server_payload(game_result, card_rank, card_suit):
    """
    Builds a PAYLOAD message sent from server to client

    The payload contains:
    - Magic cookie (4 bytes)
    - Message type = PAYLOAD (1 byte)
    - Game result (1 byte)
    - Card rank (2 bytes)
    - Card suit (1 byte)

    Parameters:
    game_result -- one of GAME_RESULT_*
    card_rank   -- card rank (1-13), or 0 if not relevant
    card_suit   -- card suit (0-3), or 0 if not relevant

    Returns:
    A bytes object - length 9
    """
    return struct.pack(SERVER_PAYLOAD_FMT, MAGIC_COOKIE, MTYPE_PAYLOAD, game_result, card_rank, card_suit)

def unpack_server_payload(data):
    """
    Parses a PAYLOAD message received from the server

    Returns:
    (cookie, message_type, game_result, card_rank, card_suit)
    """
    cookie, message_type, game_result, card_rank, card_suit = struct.unpack(SERVER_PAYLOAD_FMT, data)
    return cookie, message_type, game_result, card_rank, card_suit