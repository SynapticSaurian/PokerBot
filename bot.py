'''
Simple example pokerbot, written in Python.
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

import random


class Player(BaseBot):
    '''
    A pokerbot.
    '''

    def __init__(self) -> None:
        '''
        Called when a new game starts. Called exactly once.

        Arguments:
        Nothing.

        Returns:
        Nothing.
        '''
        pass

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        '''
        Called when a new round starts. Called NUM_ROUNDS times.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Nothing.
        '''
        my_bankroll = game_info.bankroll  # the total number of chips you've gained or lost from the beginning of the game to the start of this round
        # the total number of seconds your bot has left to play this game
        time_bank = game_info.time_bank
        round_num = game_info.round_num  # the round number from 1 to NUM_ROUNDS
        
        # your cards
        # is an array; eg: ['Ah', 'Kd'] for Ace of hearts and King of diamonds
        my_cards = current_state.my_hand

        # opponent's  revealed cards or [] if not revealed
        opp_revealed_cards = current_state.opp_revealed_cards
        
        big_blind = current_state.is_bb  # True if you are the big blind
        pass

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        '''
        Called when a round ends. Called NUM_ROUNDS times.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Nothing.
        '''
        my_delta = current_state.payoff  # your bankroll change from this round
        
        street = current_state.street  # 'pre-flop', 'flop', 'auction', 'turn', or 'river'
        # your cards
        # is an array; eg: ['Ah', 'Kd'] for Ace of hearts and King of diamonds
        my_cards = current_state.my_hand

        # opponent's revealed cards or [] if not revealed
        opp_revealed_cards = current_state.opp_revealed_cards

    def get_move(self, game_info, current_state):

        street = current_state.street
        my_cards = current_state.my_hand
        board = current_state.board
        pot = current_state.pot
        my_stack = current_state.my_chips
        opp_stack = current_state.opp_chips
        cost_to_call = current_state.cost_to_call
        in_position = not current_state.is_bb
        effective_stack = min(my_stack, opp_stack)

        # -------- AUCTION PHASE --------
        if street == "auction":
            return self.handle_auction(current_state, pot, my_stack)

        # -------- COMMON CALCULATIONS --------
        hand_bucket = self.evaluate_hand(my_cards, board)
        board_texture = self.classify_board(board)
        spr = self.compute_spr(effective_stack, pot)

        info_advantage = len(current_state.opp_revealed_cards) > 0

        # -------- STREET PLAY --------
        if street == "pre-flop":
            return self.play_preflop(current_state, hand_bucket)

        if street == "flop":
            return self.play_flop(current_state, hand_bucket, board_texture, spr, info_advantage)

        if street == "turn":
            return self.play_turn(current_state, hand_bucket, board_texture, spr, info_advantage)

        if street == "river":
            return self.play_river(current_state, hand_bucket, board_texture, spr, info_advantage)

        return ActionCheck()
    
    def handle_auction(self, current_state, pot, my_stack):

        board = current_state.board
        hand_bucket = self.evaluate_hand(current_state.my_hand, board)
        board_texture = self.classify_board(board)

        info_value = self.estimate_info_value(hand_bucket, board_texture, pot)

        max_bid = int(0.25 * my_stack)
        bid_amount = min(int(info_value), max_bid)

        return ActionBid(max(0, bid_amount))
    
    def evaluate_hand(self, my_cards, board):

        if not board:
            return self.evaluate_preflop_hand(my_cards)

        # Placeholder logic
        return "medium"

    def classify_board(self, board):

        if len(board) < 3:
            return "unknown"

        # Simple placeholder
        return "neutral"

    def compute_spr(self, effective_stack, pot):

        if pot == 0:
            return 100
        return effective_stack / pot
    
    def estimate_info_value(self, hand_bucket, board_texture, pot):

        base = pot * 0.2

        if hand_bucket in ["medium", "strong_draw"]:
            base *= 1.5

        if board_texture == "wet":
            base *= 1.5

        if hand_bucket in ["nuts", "air"]:
            base *= 0.5

        return base
    
    def play_preflop(self, state, hand_bucket):

        if hand_bucket == "premium":
            return self.raise_or_call(state)

        if hand_bucket == "trash":
            if state.can_act(ActionFold):
                return ActionFold()
            return ActionCheck()

        return self.call_or_check(state)

    def play_flop(self, state, hand_bucket, board_texture, spr, info_advantage):

        if hand_bucket in ["nuts", "very_strong"]:
            return self.raise_or_bet_big(state)

        if hand_bucket == "strong":
            return self.value_bet(state)

        if hand_bucket == "medium":
            return self.check_call(state)

        if hand_bucket == "strong_draw":
            return self.semi_bluff(state)

        return self.fold_or_check(state)
    
    def play_river(self, state, hand_bucket, board_texture, spr, info_advantage):

        if hand_bucket in ["nuts", "very_strong"]:
            return self.raise_or_bet_big(state)

        if hand_bucket == "strong":
            return self.value_bet(state)

        if hand_bucket == "medium":
            return self.check_call(state)

        return self.fold_or_check(state)
    
    def play_turn(self, state, hand_bucket, board_texture, spr, info_advantage):
        return self.play_flop(state, hand_bucket, board_texture, spr, info_advantage)


    def raise_or_call(self, state):
        if state.can_act(ActionRaise):
            min_raise, _ = state.raise_bounds
            return ActionRaise(min_raise)
        if state.can_act(ActionCall):
            return ActionCall()
        return ActionCheck()

    def raise_or_bet_big(self, state):
        if state.can_act(ActionRaise):
            min_raise, max_raise = state.raise_bounds
            return ActionRaise(min(max_raise, int(0.75 * max_raise)))
        if state.can_act(ActionCall):
            return ActionCall()
        return ActionCheck()

    def evaluate_preflop_hand(self, my_cards):

        rank_order = "23456789TJQKA"

        r1 = my_cards[0][0]
        r2 = my_cards[1][0]
        s1 = my_cards[0][1]
        s2 = my_cards[1][1]

        i1 = rank_order.index(r1)
        i2 = rank_order.index(r2)

        high = max(i1, i2)
        low = min(i1, i2)

        is_pair = r1 == r2
        is_suited = s1 == s2
        gap = abs(i1 - i2)

        # Premium
        if is_pair and high >= rank_order.index("T"):
            return "premium"
        if {r1, r2} == {"A", "K"}:
            return "premium"

        # Strong
        if is_pair and high >= rank_order.index("7"):
            return "strong"
        if high >= rank_order.index("Q") and gap <= 1:
            return "strong"

        # Playable
        if is_suited and gap <= 2:
            return "playable"
        if high >= rank_order.index("J"):
            return "playable"

        return "trash"

    def value_bet(self, state):
        if state.can_act(ActionRaise):
            min_raise, _ = state.raise_bounds
            return ActionRaise(min_raise)
        if state.can_act(ActionCall):
            return ActionCall()
        return ActionCheck()


    def check_call(self, state):
        if state.can_act(ActionCall):
            return ActionCall()
        return ActionCheck()


    def semi_bluff(self, state):
        if state.can_act(ActionRaise):
            min_raise, _ = state.raise_bounds
            return ActionRaise(min_raise)
        return self.check_call(state)


    def fold_or_check(self, state):
        if state.can_act(ActionFold):
            return ActionFold()
        return ActionCheck()


    def call_or_check(self, state):
        if state.can_act(ActionCall):
            return ActionCall()
        return ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())