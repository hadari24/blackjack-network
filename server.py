import socket
import random
import time

from protocol import (MAGIC_COOKIE, REQUEST_SIZE, SERVER_PAYLOAD_SIZE, CLIENT_PAYLOAD_SIZE, GAME_RESULT_NOTOVER, GAME_RESULT_LOSS, GAME_RESULT_TIE, GAME_RESULT_WIN, MTYPE_PAYLOAD, pack_server_payload, unpack_request, unpack_client_payload, pack_offer, unpack_offer)

SERVER_PORT = 2005
SERVER_NAME = "Bossi"

def recv_exact(sock, n):
    """
    Receives exactly n bytes from a TCP socket.

    TCP is a stream-based protocol, which means that a single recv(n)
    call is NOT guaranteed to return n bytes at once.
    This function keeps reading from the socket until exactly n bytes
    are received, or until the connection is closed.

    Parameters:
    sock -- an open TCP socket connected to a client
    n    -- number of bytes to receive

    Returns:
    A bytes object of length n.

    Raises:
    ConnectionError if the socket is closed before n bytes are received.
    """
    data = b"" # buffer to store received bytes
    while len(data) < n: # try to receive the remaining number of bytes
        chunk = sock.recv(n - len(data))
        if chunk == b"": # if recv returns empty bytes, the connection was close
            raise ConnectionError("socket closed while receiving")
        data += chunk # append the received chunk to our buffer
    return data

def create_deck():
    """
    Creates a standard 52-card deck.

    Each card is represented as a tuple:
        (rank, suit)

    Where:
    - rank: integer 1-13
        1  -> Ace
        11 -> Jack
        12 -> Queen
        13 -> King
    - suit: integer 0-3
        0 -> Clubs
        1 -> Diamonds
        2 -> Hearts
        3 -> Spades

    Returns:
    A list of 52 unique (rank, suit) tuples.
    """
    deck = []

    for card_suit in range(4): # hearts, dimonds, spades, clubs
        for card_rank in range(1, 14): # A, 2-10, J, Q, K
            deck.append((card_rank, card_suit))

    return deck

def shuffle_deck(deck):
    """
    Shuffles the given deck of cards in place.

    Parameters:
    deck -- list of (rank, suit) tuples

    Returns:
    None (the deck is shuffled in place)
    """
    random.shuffle(deck)

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

def hand_total(hand):
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
    total = 0

    for (rank, suit) in hand:
        total += rank_value(rank)

    return total


def initial_deal(deck, client_sock):
    player_hand = []
    dealer_hand = []
    dealer_hidden = None # will be the second card

    for i in range(2): # draw players cards (2 cards)
        card = deck.pop() # draw a card

        player_hand.append(card) # add to player hand

        card_rank, card_suit = card # unpack card

        # send to the player its first card
        client_sock.sendall(pack_server_payload(GAME_RESULT_NOTOVER, card_rank, card_suit))

    # draw dealer cards (first known to all and the second is hidden)
    dealer_first_card = deck.pop() # draw a card

    dealer_hand.append(dealer_first_card) # add to dealer hand
    
    dealer_first_card_rank, dealer_first_card_suit = dealer_first_card # unpack card

    # send to the player the dealers first card
    client_sock.sendall(pack_server_payload(GAME_RESULT_NOTOVER, dealer_first_card_rank, dealer_first_card_suit))

    # dealers second card
    dealer_hidden = deck.pop() # draw the second card
    
    return (player_hand, dealer_hand, dealer_hidden)
 
def player_turn(client_sock, deck, player_hand):
    """
    Handles the player's turn.

    The server waits for the client's decision:
    - "Hittt": deal another card and continue
    - "Stand": stop the player's turn

    If at any point the player's total score reaches 22 or more,
    the player is considered busted.

    Parameters:
    client_sock -- TCP socket connected to the client
    deck        -- list of remaining cards (deck.pop() draws a card)
    player_hand -- list of cards currently in the player's hand

    Returns:
    A tuple:
    (player_busted: bool)
    """
    while True: # calculate players score
        score = hand_total(player_hand)

        if score > 21: # check if player busted
            return True # player busted => lost
        
        # receive decision from client - 10 bytes
        data = recv_exact(client_sock, CLIENT_PAYLOAD_SIZE)
        cookie, msg_type, decision = unpack_client_payload(data)

        # validate protocol
        if cookie != MAGIC_COOKIE:
            raise ValueError("Invalid magic cookie from client")
        
        # handle decision
        if decision == "Hittt":
            # draw new card
            new_card = deck.pop()
            player_hand.append(new_card)

            new_rank, new_suit = new_card

            # send new card to the client
            client_sock.sendall(pack_server_payload(GAME_RESULT_NOTOVER, new_rank, new_suit))

            # continue loop if player choose hit again
        elif decision == "Stand":
            return False # player did not bust, turn ends

        else:
            raise ValueError(f"Invalid decision from client: {decision}")    

def dealer_turn(client_sock, deck, dealer_hand, dealer_hidden):
    """
    Handles the dealer's turn.

    Rules:
    - Dealer first reveals the hidden card (second dealer card) to the client.
    - Dealer then draws additional cards until the dealer's total score is 17 or higher.
    - If dealer total exceeds 21, the dealer is busted.

    Communication:
    - Every time the dealer reveals/draws a visible card, the server sends a SERVER_PAYLOAD
      with GAME_RESULT_NOTOVER and the drawn card (rank, suit).

    Parameters:
    client_sock    -- TCP socket connected to the client
    deck           -- list of remaining cards (deck.pop() draws a card)
    dealer_hand    -- list of dealer visible cards (already has the first upcard)
    dealer_hidden  -- the dealer's hidden card (rank, suit tuple)

    Returns:
    A tuple:
    (dealer_busted: bool)
    """
    # reveal the hidden card to the client
    dealer_hand.append(dealer_hidden)
    hidden_rank, hidden_suit = dealer_hidden
    client_sock.sendall(pack_server_payload(GAME_RESULT_NOTOVER, hidden_rank, hidden_suit))

    # keep draw cards until dealer reaches 17+
    while True:
        dealer_score = hand_total(dealer_hand)

        if dealer_score > 21:
            return True # dealer bust
        
        if dealer_score >= 17:
            return False # dealer stands and not bust
        
        # draw another card
        new_card = deck.pop()
        dealer_hand.append(new_card)

        new_rank, new_suit = new_card
        client_sock.sendall(pack_server_payload(GAME_RESULT_NOTOVER, new_rank, new_suit))

def who_won(player_hand, dealer_hand, player_busted, dealer_busted):
    """
    Determines the round result according to the game rules.

    Rules:
    - If the player busted (score >= 22), the player loses.
    - Else if the dealer busted (score > 21), the player wins.
    - Otherwise compare totals:
        * player > dealer -> WIN
        * player < dealer -> LOSS
        * equal -> TIE

    Parameters:
    player_hand    -- list of (rank, suit) tuples for the player
    dealer_hand    -- list of (rank, suit) tuples for the dealer
    player_busted  -- bool, True if player busted
    dealer_busted  -- bool, True if dealer busted

    Returns:
    One of:
    GAME_RESULT_WIN / GAME_RESULT_LOSS / GAME_RESULT_TIE
    """
    if player_busted:
        return GAME_RESULT_LOSS

    if dealer_busted:
        return GAME_RESULT_WIN

    player_score = hand_total(player_hand)
    dealer_score = hand_total(dealer_hand)

    if player_score > dealer_score:
        return GAME_RESULT_WIN
    if player_score < dealer_score:
        return GAME_RESULT_LOSS
    return GAME_RESULT_TIE

def end_round(client_sock, game_result):
    """
    Sends the final result of the round to the client.

    The final message contains:
    - game_result: WIN / LOSS / TIE
    - card_rank = 0
    - card_suit = 0

    Parameters:
    client_sock -- TCP socket connected to the client
    game_result -- one of GAME_RESULT_WIN / GAME_RESULT_LOSS / GAME_RESULT_TIE
    """
    client_sock.sendall(pack_server_payload(game_result, 0, 0))
 
def run_match_for_client(client_sock, rounds):
    """
    Runs a full match (multiple rounds) with a connected client.
    "the game itself"

    For each round:
    - Create and shuffle a fresh 52-card deck (no duplicates within the round)
    - initial_deal: send 2 player cards + 1 dealer upcard (dealer hole card hidden)
    - player_turn: receive Hit/Stand decisions and deal cards
    - dealer_turn: reveal hole card, draw until 17+
    - who_won: decide WIN/LOSS/TIE
    - end_round: send final game result to client

    Parameters:5
    client_sock -- TCP socket connected to the client
    rounds      -- number of rounds to play (0-255)
    """
    for r in range(rounds):
        print(f"\n[GAME] round {r+1}/{rounds}")

        # fresh deck per round
        deck = create_deck()
        shuffle_deck(deck)

        # initial deal
        player_hand, dealer_hand, dealer_hidden = initial_deal(deck, client_sock)

        # check if player busted before playing (H\S)
        if hand_total(player_hand) > 21:
            player_busted = True
            dealer_busted = False            
        else:
            # player turn
            player_busted = player_turn(client_sock, deck, player_hand)

            # dealer turn, if player not busted
            dealer_busted = False
            if not player_busted:
                dealer_busted = dealer_turn(client_sock, deck, dealer_hand, dealer_hidden)

        # decide winner + send final result
        result = who_won(player_hand, dealer_hand, player_busted, dealer_busted)
        end_round(client_sock, result)

        print(f"[GAME] round result = {result}")

def run_single_threaded_server():
    """
    This function manages the server in a single loop (Serial/Sequential flow):
    1. Send ONE UDP broadcast offer.
    2. Wait (Block) for a TCP connection.
    3. Play the game.
    4. Repeat.
    """
    # UDP for broadcast
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    UDP_DEST_PORT = 13122 # as defined in the instructions

    # hear out TCP broadcast
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("", SERVER_PORT))
    server_sock.listen(1)

    # timeout to get the server from getting stuck in .accept(), it alows us to wake up every sec and send another UDP offer
    server_sock.settimeout(1.0)

    print(f"Server started, listening on IP address... (TCP port {SERVER_PORT})")

    while True:
        client_sock = None
        addr = None

        # wait and broadcast loop
        # we stay in this loop until a client connects
        print("[UDP] broadcasting offers and waiting for client...")

        while True:
            try:
                # sending UDP offer for connection
                offer_msg = pack_offer(SERVER_PORT, SERVER_NAME)
                udp_sock.sendto(offer_msg, ('<broadcast>', UDP_DEST_PORT))

                # wait a sec to see if someone connects
                # if no connects within 1 sec, it raises a socket.timeout exception
                client_sock, addr = server_sock.accept()

                # if we got here it means someone connected
                break
            
            except socket.timeout:
                # no one came after a sec, the loop run again and we'll send another UDP
                continue
            except Exception as e:
                print(f"error: {e}")
                break
        
        # game mode
        if client_sock:
            # we cancel the timeout so it wont stuck the game
            client_sock.settimeout(None)

            print(f"[TCP] client connected from {addr}")
            try:
                # receive the initial request (name and rounds)
                req_data = recv_exact(client_sock, REQUEST_SIZE)
                cookie, msg_type, rounds, client_name = unpack_request(req_data)

                if cookie != MAGIC_COOKIE:
                    print("Invalid Cookie, dropping client.")
                else:
                    print(f"[TCP] game starting with {client_name}")
                    # run the actual game logic
                    run_match_for_client(client_sock, rounds)
            except Exception as e:
                print(f"error during game: {e}")

            finally:
                # clean up the connection so we can serve the next player
                client_sock.close()
                print("--- game finished, back to broadcasting ---")

                # wait 1 sec before screaming again
                time.sleep(1)

if __name__ == "__main__":
    run_single_threaded_server()