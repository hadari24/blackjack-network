import socket
import struct
import traceback # stanard library used to pack and unpack binary data for network transmission
from protocol import (MAGIC_COOKIE, REQUEST_SIZE, SERVER_PAYLOAD_SIZE, CLIENT_PAYLOAD_SIZE, GAME_RESULT_NOTOVER, GAME_RESULT_LOSS, GAME_RESULT_TIE, GAME_RESULT_WIN, pack_request, pack_client_payload, unpack_server_payload, unpack_offer)

def recv_exact(sock, n):
    """
    Receives exactly n bytes from a TCP socket.
    Keeps reading until the buffer is full.
    """
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if chunk == b"":
            raise ConnectionError("socket closed while receiving")
        data += chunk
    return data

def result_to_str(r):
    """
    Converts the game result byte code to a string.
    """
    if r == GAME_RESULT_NOTOVER: return "NOT OVER"
    if r == GAME_RESULT_LOSS: return "LOSS"
    if r == GAME_RESULT_WIN: return "WIN"
    if r == GAME_RESULT_TIE: return "TIE"
    return f"UNKNOWN({r})"

def rank_value(rank):
    """
    Returns the Blackjack point value of a card rank

    Scoring rules used in this implementation:
    - Cards with rank 11, 12, or 13 (Jack, Queen, King) are worth 10 points.
    - Ace is always worth 11 points.
    - Cards with ranks 2 through 10 are worth their numeric value.

    Parameters:
    rank -- integer card rank (2-11)

    Returns:
    Integer value representing the card's contribution to the hand
    """
    if rank >= 11:
        return 10
    if rank == 1:
        return 11
    return rank

def hand_total(ranks): # need to change documentation
    """
    Calculates the total score of a hand.

    Each card in the hand is a tuple: (rank, suit).
    The score of each card is determined by rank_value(rank).

    Note:
    - Ace (rank 1) is always worth 11 points.
    - No dynamic Ace adjustment is performed.

    Parameters:
    hand -- list of (rank, suit) tuples

    Returns:
    Integer representing the total score of the hand.
    """
    # total = 0

    # for rank in ranks:
    #     total += rank_value(rank)

    # return total
    return sum(ranks)

def card_to_str(rank, suit):
    """
    convert cards to string
    """
    ranks = {1: "A", 11: "J", 12: "Q", 13: "K"}
    suits = {0: "♣", 1: "♦", 2: "♥", 3: "♠"}

    r = ranks.get(rank, str(rank))
    s = suits.get(suit, "?")
    return f"{r} {s}"

def listen_to_offer():
    """
    Listens for UDP broadcast offers from the server.
    Returns the server's IP and TCP port.
    """
    UDP_PORT = 13122
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # allow multi clients to listen on the same port (multi players play with the same dealer)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    udp_sock.bind(("", UDP_PORT))

    print("client started, listening for offer requests...") # "player looking for dealer to play with..."

    while True:
        try:
            # receive UDP packet (buffer size 1024 is enough for offer)
            data, addr = udp_sock.recvfrom(1024)

            # unpack and validate
            cookie, msg_type, server_port, server_name = unpack_offer(data)

            if cookie == MAGIC_COOKIE and msg_type == 0x2: # 0x2 is OFFER
                # clean up the server name string
                server_name_clean = server_name.strip('\x00')
                print(f"Received offer from server '{server_name_clean}'")
                
                return addr[0], server_port

        except Exception as e:
            # ignore a packet and keep listening if a packet is valid
            continue

def main():
    """
    Main client execution flow

    Steps:
    1. Find server by UDP offers
    2. Connect via TCP
    3. Send REQUEST (rounds + client name)
    4. For each round:
       - Receive initial deal (2 player cards + 1 dealer upcard)
       - Player decisions (Hit/Stand)
       - Receive dealer cards until final result
    5. Close connection and print summary
    """
    while True:
        # === find a server - UDP ===
        server_ip, server_tcp_port = listen_to_offer()

        # === connect - TCP ===
        sock = None
        wins = losses = ties = 0  # define here so it's available in finally too

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((server_ip, server_tcp_port))

            # === game setup ===
            client_name = "OFRIELOV"
            try:
                rounds = int(input("How many rounds would you like to play? "))
            except ValueError:
                rounds = 3

            # send the request packet
            sock.sendall(pack_request(rounds, client_name))

            # === game loop (exactly 'rounds' rounds) ===
            for round_idx in range(rounds):
                # --- 1) initial deal: read 3 payloads (2 player + 1 dealer upcard) ---
                player_cards = []
                dealer_cards = []
                player_ranks = []

                for i in range(3):
                    data = recv_exact(sock, SERVER_PAYLOAD_SIZE)
                    cookie, msg_type, game_result, card_rank, card_suit = unpack_server_payload(data)

                    if cookie != MAGIC_COOKIE:
                        raise ValueError("Invalid cookie from server during initial deal")

                    if i < 2: # first and second cards (the player's)
                        player_cards.append(card_to_str(card_rank, card_suit))

                        player_ranks.append(rank_value(card_rank))
                    else: # the dealer known card
                        dealer_cards.append(card_to_str(card_rank, card_suit))

                print(f"{client_name} hand: {', '.join(player_cards)} || dealer hand: {', '.join(dealer_cards)}")


                # --- 2) player turn ---
                while True:
                    # check if player already busted
                    if hand_total(player_ranks) > 21:
                        print(f"{client_name} busted! with {hand_total(player_ranks)} points")
                        break
                    choice = input("Hit or Stand? (H/S): ").strip().upper()
                    if choice == "H":
                        decision = "Hittt"
                    elif choice == "S":
                        decision = "Stand"
                    else:
                        print("Please type 'H' for Hit or 'S' for Stand.")
                        continue

                    sock.sendall(pack_client_payload(decision))

                    if decision == "Stand":
                        break

                    data = recv_exact(sock, SERVER_PAYLOAD_SIZE)
                    cookie, msg_type, game_result, card_rank, card_suit = unpack_server_payload(data)

                    if cookie != MAGIC_COOKIE:
                        raise ValueError("Invalid cookie after hit")

                    player_cards.append(card_to_str(card_rank, card_suit))
                    player_ranks.append(rank_value(card_rank))

                    print(f"{client_name} hand: {', '.join(player_cards)} || dealer hand: {', '.join(dealer_cards)}")

                    player_score = hand_total(player_ranks)
                    if player_score > 21:
                        print(f"{client_name} busted! with {player_score} points")
                        break
                    if game_result != GAME_RESULT_NOTOVER:
                        break

                # dealer + result
                while True:
                    data = recv_exact(sock, SERVER_PAYLOAD_SIZE)
                    cookie, msg_type, game_result, card_rank, card_suit = unpack_server_payload(data)

                    if cookie != MAGIC_COOKIE:
                        raise ValueError("Invalid cookie during dealer turn")

                    if game_result == GAME_RESULT_NOTOVER:
                        dealer_cards.append(card_to_str(card_rank, card_suit))
                        print(f"{client_name} hand: {', '.join(player_cards)} || dealer hand: {', '.join(dealer_cards)}")
                        continue

                    if game_result == GAME_RESULT_WIN:
                        wins += 1
                    elif game_result == GAME_RESULT_LOSS:
                        losses += 1
                    elif game_result == GAME_RESULT_TIE:
                        ties += 1

                    print(f"Round {round_idx + 1} result: {result_to_str(game_result)}\n")
                    break

            print("Server finished all rounds.")

        except Exception as e:
            traceback.print_exc()
            print(f"Error: {e}")

        finally:
            if sock:
                sock.close()
            print(f"Game summary: wins={wins}, losses={losses}, ties={ties}")
            win_rate = wins / rounds
            print(f"finished playing {rounds} rounds, win rate {win_rate}")
            print("!!! Looking for a new server !!!\n")
            
if __name__ == "__main__":
    main()

