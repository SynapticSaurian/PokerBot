from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

import random

class Player(BaseBot):
    def __init__(self) -> None:
        pass

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def get_move(self, game_info, current_state):
        street = current_state.street
        my_cards = current_state.my_hand
        board = current_state.board
        pot = current_state.pot
        my_stack = current_state.my_chips
        opp_stack = current_state.opp_chips
        effective_stack = min(my_stack, opp_stack)

        # -------- AUCTION PHASE --------
        # Using your original, highly accurate auction logic
        if street == "auction":
            return self.handle_auction(current_state, pot, my_stack)

        hand_bucket = self.evaluate_hand(my_cards, board)
        
        # -------- SNEAK PEEK INTEGRATION --------
        # If we saw a card, we adjust our confidence (but we DO NOT auto-fold)
        info_advantage = len(current_state.opp_revealed_cards) > 0
        if info_advantage and board:
            hand_bucket = self.adjust_for_revealed_cards(hand_bucket, current_state)

        if street == "pre-flop":
            return self.play_preflop(current_state, hand_bucket)

        # Unified post-flop logic that includes bluffs and pot-relative sizing
        if street in ["flop", "turn", "river"]:
            return self.postflop_strategy(current_state, hand_bucket, pot, info_advantage)

        return ActionCheck()

    def adjust_for_revealed_cards(self, bucket, state):
        """Downgrades hand strength if opponent's revealed card is scary, instead of auto-folding."""
        rev_card = state.opp_revealed_cards[0]
        board_ranks = [c[0] for c in state.board]
        
        # If the opponent's card completes a pair on board or is an Ace
        is_scary = rev_card[0] in board_ranks or rev_card[0] == 'A'
        
        if is_scary:
            if bucket == "nuts": return "very_strong"
            if bucket == "very_strong": return "strong"
            if bucket == "strong": return "medium"
            if bucket == "medium": return "air"
        return bucket

    def postflop_strategy(self, state, bucket, pot, info_advantage):
        """New Aggressive-Adaptive logic to climb the leaderboard."""
        if state.street == "river" and bucket == "strong_draw":
            bucket = "air"
        cost = state.cost_to_call
        
        min_r, max_r = state.raise_bounds if state.can_act(ActionRaise) else (0, 0)

        # 1. VALUE BETTING (Nuts and Very Strong)
        if bucket in ["nuts", "very_strong"]:
            if state.can_act(ActionRaise):
                # Bet larger if we have info advantage to punish blind opponents
                sizing = 0.65 if info_advantage else 0.55
                bet = max(min_r, min(int(sizing * pot), max_r))
                return ActionRaise(bet)
            if state.can_act(ActionCall):
                return ActionCall()
            return ActionCheck()

        # 2. SEMI-BLUFFING (Strong Draws)
        if bucket == "strong_draw":
            if state.can_act(ActionRaise) and random.random() < 0.35: # 35% chance to semi-bluff
                bet = max(min_r, min(int(0.5 * pot), max_r))
                return ActionRaise(bet)
            if state.can_act(ActionCall) and cost < 0.4 * pot:
                return ActionCall()
            return self.fold_or_check(state)

        # 3. INFORMATION BLUFFING (Using the Sneak Peek)
        if bucket == "air" and info_advantage and state.can_act(ActionRaise):
            opp_card_rank = state.opp_revealed_cards[0][0]
            if opp_card_rank in "23456" and random.random() < 0.30:
                bet = max(min_r, min(int(0.35 * pot), max_r))
                return ActionRaise(bet)

        # 4. DEFENSIVE CALLING (Pot Odds for Medium/Strong hands)
        if bucket in ["strong", "medium"]:
            # If cost is cheap (less than 40% of pot for strong, 25% for medium), call.
            threshold = 0.4 * pot if bucket == "strong" else 0.25 * pot
            if cost <= threshold:
                if state.can_act(ActionCall):
                    return ActionCall()
                return ActionCheck()
            
        return self.fold_or_check(state)

    def handle_auction(self, current_state, pot, my_stack):
        board = current_state.board
        hand_bucket = self.evaluate_hand(current_state.my_hand, board)
        board_texture = self.classify_board(board)

        effective_stack = min(current_state.my_chips, current_state.opp_chips)
        spr = self.compute_spr(effective_stack, pot)
        info_value = self.estimate_info_value(hand_bucket, board_texture, pot, spr, my_stack)

        bid_amount = int(info_value)
        return ActionBid(max(0, bid_amount))
        
    def evaluate_hand(self, my_cards, board):
        if not board:
            return self.evaluate_preflop_hand(my_cards)

        all_cards = my_cards + board
        rank_map = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
                    'T':10,'J':11,'Q':12,'K':13,'A':14}

        suit_counts = {}
        for card in all_cards:
            suit = card[1]
            suit_counts[suit] = suit_counts.get(suit, 0) + 1

        flush = max(suit_counts.values()) >= 5
        flush_draw = max(suit_counts.values()) == 4

        rank_counts = {}
        for card in all_cards:
            rank = card[0]
            rank_counts[rank] = rank_counts.get(rank, 0) + 1

        counts = sorted(rank_counts.values(), reverse=True)

        ranks = set(rank_map[c[0]] for c in all_cards)
        ranks = sorted(ranks)

        if 14 in ranks:
            ranks.append(1)   # wheel straight

        straight = False
        for i in range(len(ranks)-4):
            if ranks[i+4] - ranks[i] == 4:
                straight = True
                break

        if flush and straight: return "nuts"
        if counts[0] == 4: return "nuts"
        if counts[0] == 3 and counts[1] >= 2: return "nuts"
        if flush: return "very_strong"
        if straight: return "very_strong"
        if counts[0] == 3: return "very_strong"
        if counts[0] == 2 and counts[1] == 2: return "strong"
        if counts[0] == 2: return "medium"
        if flush_draw: return "strong_draw"
        return "air"

    def classify_board(self, board):
        if len(board) < 3: return "unknown"
        ranks = [card[0] for card in board]
        if len(set(ranks)) < len(ranks): return "paired"
        suits = [card[1] for card in board]
        suit_counts = {}
        for suit in suits:
            suit_counts[suit] = suit_counts.get(suit, 0) + 1
        if max(suit_counts.values()) >= 2: return "wet"
        
        rank_map = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
        rank_values = sorted(rank_map[r] for r in ranks)
        if max(rank_values) - min(rank_values) <= 4: return "wet"
        return "dry"

    def compute_spr(self, effective_stack, pot):
        if pot == 0: return 100
        return effective_stack / pot
    
    def estimate_info_value(self, hand_bucket, board_texture, pot, spr, my_stack):
        floor = max(80, int(0.10 * pot))
        if hand_bucket == "medium": value = pot * 0.45
        elif hand_bucket == "strong_draw": value = pot * 0.35
        elif hand_bucket == "strong": value = pot * 0.25
        elif hand_bucket == "very_strong": value = pot * 0.12
        elif hand_bucket == "nuts": value = pot * 0.08
        else: value = pot * 0.10

        if board_texture == "wet": value *= 1.30
        elif board_texture == "paired": value *= 1.05
        else: value *= 0.90

        if spr > 8: value *= 1.30
        elif spr > 5: value *= 1.20
        elif spr < 2: value *= 0.80
            
        value = max(value, floor)
        value = min(value, 0.60 * pot)
        return int(value)
    
    def play_preflop(self, state, hand_bucket):

        if state.cost_to_call > 700:
            if hand_bucket in ["premium", "strong"]:
                return ActionCall()
            return ActionFold()

        if hand_bucket == "premium":
            if state.can_act(ActionRaise):
                min_raise, _ = state.raise_bounds
                return ActionRaise(min_raise)
            if state.can_act(ActionCall):
                return ActionCall()
            return ActionCheck()

        if hand_bucket == "trash":
            if state.cost_to_call > 0 and state.can_act(ActionFold):
                return ActionFold()
            return ActionCheck()

        if state.can_act(ActionCall):
            return ActionCall()

        return ActionCheck()

    def evaluate_preflop_hand(self, my_cards):
        rank_order = "23456789TJQKA"
        r1, r2 = my_cards[0][0], my_cards[1][0]
        s1, s2 = my_cards[0][1], my_cards[1][1]
        i1, i2 = rank_order.index(r1), rank_order.index(r2)
        high, low = max(i1, i2), min(i1, i2)
        is_pair, is_suited = r1 == r2, s1 == s2
        gap = abs(i1 - i2)

        if is_pair and high >= rank_order.index("T"): return "premium"
        if {r1, r2} == {"A", "K"}: return "premium"
        if is_pair and high >= rank_order.index("7"): return "strong"
        if high >= rank_order.index("Q") and gap <= 1: return "strong"
        if is_suited and gap <= 2: return "playable"
        if high >= rank_order.index("J"): return "playable"
        return "trash"

    def fold_or_check(self, state):
        if state.cost_to_call > 0 and state.can_act(ActionFold):
            return ActionFold()
        return ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())