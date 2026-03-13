"""
game.py – Core XO logic, Minimax AI, bot characters, move analysis.
"""

import random

EMPTY = 0
X     = 1    # human  → ❌
O     = -1   # bot    → ⭕

WIN_COMBOS = [
    (0,1,2),(3,4,5),(6,7,8),
    (0,3,6),(1,4,7),(2,5,8),
    (0,4,8),(2,4,6),
]

CELL_EMOJI = {EMPTY: "⬜", X: "❌", O: "⭕"}


# ─────────────────────────────────────────────────────────
#  BOT CHARACTERS
# ─────────────────────────────────────────────────────────
CHARACTERS = {
    "devil": {
        "name":  "😈 The Devil",
        "intro": "😈 *The Devil* has entered the game.\n_\"Your soul is mine.\"_",
        "win":   [
            "😈 Did you really think you could beat ME?",
            "🔥 Burned. Absolutely burned.",
            "💀 Error 666: Your win not found.",
            "😈 I've seen better plays from a toddler.",
            "🔥 Your suffering brings me joy.",
        ],
        "lose":  [
            "😤 A fluke. JUST a fluke.",
            "😡 This isn't over. I WILL have my revenge.",
            "🔥 I let you win. Obviously.",
        ],
        "draw":  [
            "😈 I was going easy on you.",
            "🔥 A temporary mercy. Next time — no.",
        ],
        "think": [
            "😈 *Consulting the dark arts...*",
            "🔥 *Summoning forbidden strategies...*",
            "💀 *Calculating your demise...*",
        ],
    },
    "nerd": {
        "name":  "🤓 The Nerd",
        "intro": "🤓 *The Nerd* is ready.\n_\"Statistically, I will win 94.7% of the time.\"_",
        "win":   [
            "🤓 Precisely as calculated. My model was 97.2% confident.",
            "📊 Center + corner opening: 68% win rate. Proven.",
            "🤓 Your move sequence is a known losing pattern. See: Berlekamp 1991.",
            "💻 Algorithm executed flawlessly. Result: expected.",
        ],
        "lose":  [
            "🤓 Fascinating. I must recalibrate my decision tree.",
            "📊 My model assigned 2.3% probability to this. Noted.",
            "💻 Logging anomaly. Initiating post-game analysis...",
        ],
        "draw":  [
            "🤓 A draw. Both players played optimally from move 3.",
            "📊 Expected outcome when both parties use minimax correctly.",
        ],
        "think": [
            "🤓 *Cross-referencing 47,293 game databases...*",
            "📊 *Running alpha-beta pruning depth 9...*",
            "💻 *Evaluating 8 candidate moves...*",
        ],
    },
    "grandma": {
        "name":  "😴 Grandma",
        "intro": "😴 *Grandma* wants to play!\n_\"She's been practicing since 1987.\"_",
        "win":   [
            "😴 Oh my, I won! Would you like some cookies, dear?",
            "🍪 Grandma got you! Don't feel bad, sweetie.",
            "😊 Oh goodness! I haven't won since bingo night!",
            "🌸 That was so fun! You almost had me on move 4, dear.",
        ],
        "lose":  [
            "😴 Oh well, you're so clever! Just like your grandfather.",
            "🍪 You won! Here, have a virtual cookie 🍪",
            "😊 Oh you're too good for old Grandma!",
        ],
        "draw":  [
            "😴 A tie! How nice, nobody had to lose.",
            "🌸 We're perfectly matched, dear.",
        ],
        "think": [
            "😴 *Hmm... let me think, dear...*",
            "🌸 *One moment, adjusting my glasses...*",
            "😴 *Now where did I put my strategy...*",
            "🍪 *Thinking while the cookies bake...*",
        ],
    },
}

DEFAULT_CHARACTER = "nerd"


def char_thinking(character: str) -> str:
    c = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
    return random.choice(c["think"])

def char_result_msg(character: str, result: str) -> str:
    """result: 'win' (bot won) | 'lose' (bot lost) | 'draw'"""
    c = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
    msgs = c.get(result, c["win"])
    return "\n\n_" + random.choice(msgs) + "_"


# ─────────────────────────────────────────────────────────
#  BOARD LOGIC
# ─────────────────────────────────────────────────────────

def make_board() -> list:
    return [EMPTY] * 9

def check_winner(board: list):
    for a, b, c in WIN_COMBOS:
        if board[a] == board[b] == board[c] != EMPTY:
            return board[a]
    return None

def is_draw(board: list) -> bool:
    return EMPTY not in board and check_winner(board) is None

def available_moves(board: list) -> list:
    return [i for i, v in enumerate(board) if v == EMPTY]

def board_to_emoji(board: list) -> str:
    return "\n".join(
        "".join(CELL_EMOJI[board[r*3+c]] for c in range(3))
        for r in range(3)
    )


# ─────────────────────────────────────────────────────────
#  MINIMAX
# ─────────────────────────────────────────────────────────

def _minimax(board, depth, is_max, alpha, beta) -> int:
    w = check_winner(board)
    if w == O:         return 10 - depth
    if w == X:         return depth - 10
    if is_draw(board): return 0
    if is_max:
        best = -100
        for i in available_moves(board):
            board[i] = O
            best  = max(best, _minimax(board, depth+1, False, alpha, beta))
            board[i] = EMPTY
            alpha = max(alpha, best)
            if beta <= alpha: break
        return best
    else:
        best = 100
        for i in available_moves(board):
            board[i] = X
            best  = min(best, _minimax(board, depth+1, True, alpha, beta))
            board[i] = EMPTY
            beta  = min(beta, best)
            if beta <= alpha: break
        return best

def minimax_score(board: list) -> int:
    return _minimax(board[:], 0, True, -100, 100)

def bot_move(board: list, difficulty: str = "hard") -> int:
    moves = available_moves(board)
    if not moves: return -1
    if difficulty == "easy"   and random.random() < 0.65: return random.choice(moves)
    if difficulty == "medium" and random.random() < 0.35: return random.choice(moves)
    best_score, best_move = -100, moves[0]
    for i in moves:
        board[i] = O
        score    = _minimax(board, 0, False, -100, 100)
        board[i] = EMPTY
        if score > best_score:
            best_score, best_move = score, i
    return best_move


# ─────────────────────────────────────────────────────────
#  POST-GAME ANALYSIS
# ─────────────────────────────────────────────────────────

def analyse_game(move_history: list) -> str:
    """
    move_history: list of (board_snapshot, player_mark, cell_idx)
    Returns a one-line analysis string, or "" if too short.
    """
    if len(move_history) < 3:
        return ""
    prev_score     = 0
    turning_cell   = None
    turning_player = None
    for board_snap, player_mark, cell_idx in move_history:
        score = minimax_score(board_snap)
        if abs(prev_score) < 3 and abs(score) >= 5:
            turning_cell   = cell_idx
            turning_player = player_mark
            break
        prev_score = score
    if turning_cell is None:
        _, turning_player, turning_cell = move_history[-1]
    cell_num = turning_cell + 1
    row = turning_cell // 3 + 1
    col = turning_cell % 3  + 1
    if turning_player == X:
        return f"🔍 *Analysis:* Cell {cell_num} (row {row}, col {col}) was the winning move — the game was decided there."
    else:
        return f"🔍 *Analysis:* The bot's move to cell {cell_num} (row {row}, col {col}) forced the result — the board was lost from that point."


# ─────────────────────────────────────────────────────────
#  GAME-STATE FACTORIES
# ─────────────────────────────────────────────────────────

def new_pvp_game(p1_id, p2_id, p1_name, p2_name) -> dict:
    return {
        "mode": "pvp", "status": "playing",
        "board": make_board(),
        "players": {p1_id: X, p2_id: O},
        "names":   {p1_id: p1_name, p2_id: p2_name},
        "turn": p1_id, "x_player": p1_id, "o_player": p2_id,
        "tournament": False, "blitz": False,
        "move_history": [], "msg_id": None,
    }

def new_pve_game(player_id, player_name,
                 difficulty="hard", character=DEFAULT_CHARACTER,
                 revenge=False) -> dict:
    char_name = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])["name"]
    return {
        "mode": "pve", "status": "playing",
        "board": make_board(),
        "players": {player_id: X},
        "names":   {player_id: player_name, "bot": char_name},
        "turn": player_id, "x_player": player_id, "o_player": "bot",
        "difficulty": difficulty, "character": character,
        "tournament": False, "revenge": revenge,
        "move_history": [], "msg_id": None,
    }
