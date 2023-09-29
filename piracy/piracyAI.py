import re
from random import shuffle

# constants to change
PRUNING = True
MAX_PLY = 12

# constants to leave alone
LEFT_PLAYER  =  1
RIGHT_PLAYER = -1
DIRECTIONS = {"a":0, "d":1, "u":-1}
INF     =  1000000000  # close enough ;)
NEG_INF = -1000000000

# global inits
ai_positions_considered = 0
max_level = 0


def clone_board(board):
    return [row[:] for row in board]


# True if a player has at least one pirate on the ropes
def player_is_on_ropes(board, player):
    for r in range(5):
        for c in range(1,7):
            pos = board[r][c]
            if pos is not None and pos != 0 and pos ^ player >= 0:  # signs must match
                return True
    return False


def print_board(board):
    for r in range(5):
        for c in range(8):
            if board[r][c] is None:
                display = ' X'
            else:
                display = str(board[r][c])
                if len(display) == 1:
                    display = " " + display
            if c < 7:
                print(display + "|", end='')
            else:
                print(display)
        if r < 4:
            print("--+"*7 + "--")
    print()


# return pirate counts for LEFT_PLAYER and RIGHT_PLAYER
def get_pirate_counts(board, player):
    return board_eval(board, player)[1:3]


def is_game_over(board):
    return board_eval(board, LEFT_PLAYER)[3]


# The static evaluation function (aka heuristic evaluation function)
# the value of the board at a given moment (with additional lookahead)
# the higher the score, the better for the passed-in player
def static_eval_func(board, player_to_max):
    return board_eval(board, player_to_max)[0]


# TODO: this has no notion of board control, just pirate and non-blown hatch values.
#       Kinda weak, but good enough if there's sufficient look ahead.
def board_eval(board, player_to_max):
    score = 0  # positive is good for player_to_max
    left_pirate_count = 0
    right_pirate_count = 0
    game_over = False
    gunport_value = 1  # value of a non-blown (not None) hatch

    for r in range(5):
        for c in range(8):
            pos = board[r][c]
            if pos is None:
                continue

            if pos > 0:
                left_pirate_count += pos
            elif pos < 0:
                right_pirate_count -= pos

            score += pos * player_to_max
            if c == 0:
                score += gunport_value * player_to_max
            elif c == 7:
                score += -1 * gunport_value * player_to_max

    if right_pirate_count == 0:
        score = 10000 * player_to_max  # value must be smaller than INF
        game_over = True
    elif left_pirate_count == 0:
        score = -10000 * player_to_max  # value must be larger than NEG_INF
        game_over = True

    return (score, left_pirate_count, right_pirate_count, game_over)


def cannon_col_for_player(player):
    if player == LEFT_PLAYER:
        return 0  # left cannons
    else:
        return 7  # right cannons


# launch one or more pirates from cannons into a new board state
def process_pirate_launch(board, player, rows_bitmap):
    cannon_col = cannon_col_for_player(player)
    new_state = clone_board(board)

    for row in range(5):
        use_cannon = rows_bitmap & 1 > 0
        rows_bitmap >>= 1
        if not use_cannon:
            continue
        new_state[row][cannon_col] -= player  # launch pirate
        new_state[row][cannon_col + player] = player  # kill any pirate already there (friend or foe)

    return new_state


# move pirates on a new board state
def process_pirate_move(board, player, r_delta):
    if player == LEFT_PLAYER:
        loop_params = (6, 0, -1)  # process right to left
    else:
        loop_params = (1, 7, 1)   # process left to right

    new_state = clone_board(board)

    for c in range(*loop_params):
        for r in range(5):
            pos = new_state[r][c]
            if pos is None or pos == 0 or pos ^ player < 0:
                continue
            new_state[r][c] = 0  # move pirate
            new_c = c + player
            if new_c == 0 or new_c == 7:  # if a cannon col
                new_state[r][new_c] = None  # always across, no diag, and blow the hatch
                opp_c = (new_c + player) % 8
                if (new_state[r][opp_c] is not None and
                    abs(new_state[r][opp_c]) < 3):
                    new_state[r][opp_c] += player  # reappear in opposite cannon hold (horz playfield wrap)
            else:
                new_r = (r + r_delta) % 5  # remove pirate from current position, handle any vert playfield wrap
                if new_state[new_r][new_c] is not None:  # if not broken ropes
                    new_state[new_r][new_c] = player  # complete move

    return new_state


def cannon_can_launch(board, player, row):
    cannon_col = cannon_col_for_player(player)
    return board[row][cannon_col] is not None and board[row][cannon_col] != 0


def cannons_can_launch(board, player, rows_bitmap):
    if rows_bitmap == 0:
        return False
    for row in range(5):
        if rows_bitmap & 1 > 0:
            if not cannon_can_launch(board, player, row):
                return False
        rows_bitmap >>= 1  
    return True


# search space is small enough that this can afford to generate all possible moves from a given
# state, not just a few heuristically-promising ones.
def get_next_positions(board, player, describe_move = False):
    new_states = []

    # if player has one or more pirates on ropes, add 3 new states
    if player_is_on_ropes(board, player):
        for direction in DIRECTIONS.keys():  # across, diag down, diag up
            new_state = process_pirate_move(board, player, DIRECTIONS[direction])
            if describe_move:
                new_state[5] = 'direction %s' % direction
            new_states.append(new_state)

    # create 0 to 31 new states for cannon-launched pirates   
    options = []
    mask = 0
    for r in range(5):
        if cannon_can_launch(board, player, r):
            bit = 2**r
            mask |= bit  # appends bits for cannons that can launch
            options.append(bit)
    shuffle(options)

    # Created single cannon launch options up front, so they are more strongly
    # selected when board outcomes look similar.  Now create the rest.      
    for r in range(3, 32):
        option = r & mask
        if option != 0 and option not in options:
            options.append(option)

    for rows_bitmap in options:
        new_state = process_pirate_launch(board, player, rows_bitmap)
        if describe_move:
            new_state[5] = 'cannon launch %s' % format(rows_bitmap, '05b')
        new_states.append(new_state)

    return new_states


# player_to_max remains unchanged throughout the recursive calls
# max_ply == 0 will just evaluate the passed-in position without look-ahead
def minimax(position, max_ply, player_to_max):
    global max_level
    max_level = max_ply
    return _minimax(position, 0, player_to_max, True, NEG_INF, INF)


# Param defaults are just for initial entry into recursion
def _minimax(curr_position, level, player_to_max, max_the_level, alpha, beta):
    global ai_positions_considered
    ai_positions_considered += 1

    # no children or not exploring children, return:
    if level == max_level:
        return (static_eval_func(curr_position, player_to_max), curr_position)
    if max_the_level:
        next_positions = get_next_positions(curr_position, player_to_max, level==0)
    else:
        next_positions = get_next_positions(curr_position, player_to_max*-1, level==0)
    if len(next_positions) == 0:  # game must be over
        return (static_eval_func(curr_position, player_to_max), curr_position)

    # explore children, select child, return:
    if max_the_level:
        max_val = NEG_INF
        max_position = None
        for child_pos in next_positions:
            (evaluation, _) = _minimax(child_pos, level + 1, player_to_max, False, alpha, beta)
            if evaluation > max_val:
                max_val = evaluation
                max_position = child_pos
            # alpha is the minimum score that the maximizing player is assured of    
            # alpha = max(alpha, evaluation)  # so-called "fail-soft" assignment order
            if PRUNING and max_val >= beta:
                break  # prune tree search
            alpha = max(alpha, max_val)  # so-called "fail-hard" assignment order
        return (max_val, max_position)
    else:
        min_val = INF
        min_position = None
        for child_pos in next_positions:
            (evaluation, _) = _minimax(child_pos, level + 1, player_to_max, True, alpha, beta)
            if evaluation < min_val:
                min_val = evaluation
                min_position = child_pos
            # beta is the maximum score that the minimizing player is assured of    
            # beta = min(beta, evaluation)  # so-called "fail-soft" assignment order
            if PRUNING and min_val <= alpha:
                break  # prune tree search
            beta = min(beta, min_val)  # so-called "fail-hard" assignment order
        return (min_val, min_position)


def main():
    global ai_positions_considered

    help = 'enter [5-digit binary], "u", "a", "d", "ply [int]", "undo", or "help"'

    # positive values for left player, negative for right
    # Nones for rope hole squares and for blown hatches
    # therefore, ropes have values None, -1, 0, or 1
    # and holds have values None or -3 through 3
    board = [
        [3,    0,    0,    0,    0,    0,    0,   -3],
        [3,    0, None,    0,    0, None,    0,   -3],
        [3,    0,    0,    0,    0,    0,    0,   -3],
        [3,    0, None,    0,    0, None,    0,   -3],
        [3,    0,    0,    0,    0,    0,    0,   -3],
        ['']        
    ]

    lookahead_levels = 6
    player_to_max = LEFT_PLAYER
    c64_turn_undo = []

    print("Initial board:")
    print_board(board)

    # Created a playloop that assumes this python program is the LEFT_PLAYER having
    # the 1st move, and the C64 is the RIGHT_PLAYER.  User enters C64 moves into
    # this code, and enters python moves into C64.
    # This could be generalized of course (i.e., python on right, or python vs python).
    while(not is_game_over(board)):
        ai_positions_considered = 0
        score, board = minimax(board, lookahead_levels, player_to_max)
        print("Python's move: %s" % board[5])
        print("Python's board evaluation: %d, lookahead: %d,\npositions considered: %d" %
            (score, lookahead_levels, ai_positions_considered))
        print_board(board)
        c64_turn_undo.append(board)

        if is_game_over(board):
            break

        bad_input = True
        while(bad_input):
            c64_move = input("Enter C64's move >")
            c64_move = c64_move.strip().lower()
            # process undo (for if/when I enter a C64 move incorrectly)
            if c64_move == "help":
                print(help)
            elif c64_move == "undo":
                if len(c64_turn_undo) > 1:
                    c64_turn_undo = c64_turn_undo[:-1]
                    board = c64_turn_undo[-1]
                    print("Undo-ing c64's move #%d" % len(c64_turn_undo))
                    print_board(board)
                else:
                    print("Nothing to undo")
            elif c64_move.startswith("ply"):
                new_ply = int(c64_move.split(" ")[1])
                if 1 <= new_ply <= MAX_PLY:
                    lookahead_levels = new_ply
                    print("Will look ahead %d levels" % lookahead_levels)
                else:
                    print("ply out of range (1 to %d)" % MAX_PLY)
            # process cannon launch
            elif re.match("[0|1]{5}", c64_move) is not None:
                # five bits, top cannon is LSB
                # leading zeros (if bottom cannons not putting out pirates)
                rows_bitmap = int(c64_move, 2)
                if not cannons_can_launch(board, RIGHT_PLAYER, rows_bitmap):
                    print("Illegal input:  one or more cannons cannot launch")
                else:
                    board = process_pirate_launch(board, RIGHT_PLAYER, rows_bitmap)
                    bad_input = False
            # process move on ropes
            elif c64_move in ("u", "a", "d"):
                if not player_is_on_ropes(board, RIGHT_PLAYER):
                    print("Illegal input:  no pirates on ropes")
                else:
                    board = process_pirate_move(board, RIGHT_PLAYER, DIRECTIONS[c64_move])
                    bad_input = False
            else:
                print('Illegal input:  %s' % help)

        print("C64's move:")
        print_board(board)

    print("Game over")


if __name__ == "__main__":
    main()
