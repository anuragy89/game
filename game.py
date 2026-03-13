"""
game.py – Core XO game logic + Minimax AI with alpha-beta pruning
"""

import random

EMPTY = 0
X     = 1   # human / challenger  →  ❌
O     = -1  # opponent / bot      →  ⭕

WIN_COMBOS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # cols
    (0, 4, 8), (2, 4, 6),               # diagonals
]

CELL_EMOJI = {EMPTY: "⬜", X: "❌", O: "⭕"}


def make_board() -> list:
    return [EMPTY] * 9


def check_winner(board: list):
    """Returns X, O, or None."""
    for a, b, c in WIN_COMBOS:
        if board[a] == board[b] == board[c] != EMPTY:
            return board[a]
    return None


def is_draw(board: list) -> bool:
    return EMPTY not in board and check_winner(board) is None


def available_moves(board: list) -> list:
    return [i for i, v in enumerate(board) if v == EMPTY]


def board_to_emoji(board: list) -> str:
    rows = []
    for r in range(3):
        rows.append("".join(CELL_EMOJI[board[r * 3 + c]] for c in range(3)))
    return "\n".join(rows)


# ── Minimax + alpha-beta pruning ──────────────────────────

def _minimax(board: list, depth: int, is_max: bool, alpha: int, beta: int) -> int:
    winner = check_winner(board)
    if winner == O:    return 10 - depth
    if winner == X:    return depth - 10
    if is_draw(board): return 0

    if is_max:
        best = -100
        for i in available_moves(board):
            board[i] = O
            best  = max(best, _minimax(board, depth + 1, False, alpha, beta))
            board[i] = EMPTY
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best
    else:
        best = 100
        for i in available_moves(board):
            board[i] = X
            best  = min(best, _minimax(board, depth + 1, True, alpha, beta))
            board[i] = EMPTY
            beta  = min(beta, best)
            if beta <= alpha:
                break
        return best


def bot_move(board: list, difficulty: str = "hard") -> int:
    """Returns the best cell index for the bot (O) to play."""
    moves = available_moves(board)
    if not moves:
        return -1

    if difficulty == "easy" and random.random() < 0.65:
        return random.choice(moves)
    if difficulty == "medium" and random.random() < 0.35:
        return random.choice(moves)

    best_score = -100
    best_move  = moves[0]
    for i in moves:
        board[i] = O
        score    = _minimax(board, 0, False, -100, 100)
        board[i] = EMPTY
        if score > best_score:
            best_score = score
            best_move  = i
    return best_move


# ── Game-state factories ──────────────────────────────────

def new_pvp_game(p1_id: int, p2_id: int, p1_name: str, p2_name: str) -> dict:
    return {
        "mode":       "pvp",
        "status":     "playing",
        "board":      make_board(),
        "players":    {p1_id: X, p2_id: O},
        "names":      {p1_id: p1_name, p2_id: p2_name},
        "turn":       p1_id,
        "x_player":   p1_id,
        "o_player":   p2_id,
        "tournament": False,
        "msg_id":     None,
    }


def new_pve_game(player_id: int, player_name: str, difficulty: str = "hard") -> dict:
    return {
        "mode":       "pve",
        "status":     "playing",
        "board":      make_board(),
        "players":    {player_id: X},
        "names":      {player_id: player_name, "bot": "🤖 XO Bot"},
        "turn":       player_id,
        "x_player":   player_id,
        "o_player":   "bot",
        "difficulty": difficulty,
        "tournament": False,
        "msg_id":     None,
    }
