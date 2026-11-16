# All the settings for the tracker live here.

# ---- camera ----
CAMERA_ORDER = [1, 0]     # tries camera 1 first (MacBook when an iPhone is nearby), then 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ---- detection ----
PERSISTENCE_SECONDS = 0.5     # a touch must last this long before it counts
GRACE_SECONDS = 0.2           # a gap this short does not end a touch
PERSISTENCE_FRAMES = 15       # only used by train.py's offline baseline (about 0.5 sec at 30 fps)
NEAR_FRACTION = 0.09          # a finger must be this close to a face point (fraction of face width)
EYE_RADIUS = 0.08             # how close to the eyes/eyebrows counts as "eyes"
NOSE_RADIUS = 0.08
MOUTH_RADIUS = 0.08
MAX_HAND_RATIO = 1.1          # before calibration: ignore hands that look too big
CALIBRATION_TOLERANCE = 1.2   # after calibration: hand can be this much bigger than baseline
FACE_LOST_FRAMES = 10         # keep using the last face position this long if a hand hides the face

# ---- alerts ----
SOUNDS_ENABLED = True
COOLDOWN_SECONDS = 5          # min seconds between sounds
MAC_SOUNDS = {                # a different sound for each region
    "eyes": "Tink",
    "nose": "Pop",
    "mouth": "Ping",
    "forehead": "Purr",
    "cheek_chin": "Bottle",
}
WINDOWS_BEEPS = {             # frequencies in Hz
    "eyes": 1000,
    "nose": 800,
    "mouth": 600,
    "forehead": 1200,
    "cheek_chin": 700,
}

# ---- escalation (desktop notification if it keeps happening) ----
ESCALATION_COUNT = 3              # this many touches...
ESCALATION_WINDOW_MIN = 10        # ...within this many minutes
NOTIFICATION_COOLDOWN_MIN = 10    # don't send notifications more often than this

# ---- snooze ----
SNOOZE_MINUTES = 10
ALERT_DISPLAY_SECONDS = 2.0   # keep an alert on screen at least this long (display only)

# ---- files ----
DATA_DIR = "data"

# ---- look ----
REGION_NAMES = {
    "eyes": "Eyes",
    "nose": "Nose",
    "mouth": "Mouth",
    "forehead": "Forehead",
    "cheek_chin": "Cheek / chin",
}
LINE_COLOR = (235, 200, 150)      # soft blue (BGR)
ALERT_COLOR = (110, 110, 235)     # soft coral
SNOOZE_COLOR = (170, 170, 170)    # gray
JOINT_COLOR = (255, 255, 255)

# ---- automatic calibration ----
AUTO_CALIBRATE = True         # learn the hand-size baseline from your own touches
AUTOCAL_TIGHT_FRACTION = 0.04 # a fingertip this close to the face counts as a sure touch
AUTOCAL_HOLD_FRAMES = 20      # a sure touch must last this long before it is used
AUTOCAL_MIN_SAMPLES = 60      # samples needed before the baseline is set
AUTOCAL_MAX_SAMPLES = 600     # keeps the most recent samples (running median)
AUTOCAL_OUTLIER = 0.3         # ignore samples more than 30% away from the current baseline

# ---- behavior classifier ----
LABELS = ["none", "hover", "benign", "nail_biting", "skin_picking", "eye_rubbing"]
HABIT_LABELS = ["nail_biting", "skin_picking", "eye_rubbing"]
BEHAVIOR_NAMES = {
    "none": "Idle",
    "hover": "Hovering (no touch)",
    "benign": "Harmless / idle",
    "nail_biting": "Nail biting",
    "skin_picking": "Skin picking",
    "eye_rubbing": "Eye rubbing",
}
DATASET_DIR = "dataset"
MODEL_PATH = "model.joblib"
COUNTDOWN_SECONDS = 3         # collect.py: time to get your hand in position
RECORD_SECONDS = 15           # collect.py: length of each clip
WINDOW_FRAMES = 30            # frames the classifier looks at (about 1 sec)
WINDOW_STRIDE = 10            # train.py: step between training windows
CLASSIFY_EVERY = 10            # tracker.py: re-check the last window every this many frames
TRIM_FRAMES = 15              # frames cut from the start/end of each clip when training
CLASSIFIER_THRESHOLD = 0.6    # habit probability needed to count as a habit
CLASSIFIER_CONFIRM = 2        # this many windows in a row before alerting
NAIL_BITING_NEEDS_MOUTH = False  # only allow "nail biting" when the contact is at the mouth (or just under the nose)

# ---- learning from corrections (tracker.py) ----
FEEDBACK_FRAMES = 90          # how much recent footage a correction key saves (about 3 sec)
FEEDBACK_KEYS = {             # key -> what the last few seconds really were
    "x": "benign",            # X = that was NOT a habit
    "b": "nail_biting",       # B = that was nail biting
    "p": "skin_picking",      # P = that was skin picking
    "e": "eye_rubbing",       # E = that was eye rubbing
}

# ---- training clean-up ----
CLEAN_WINDOWS = True          # drop windows from harmless/habit clips where the hand never comes near the face
MERGE_IDLE_INTO_HARMLESS = True   # train idle and harmless contact as one "not a habit" class

# ---- database (all events go to SQLite as well as the CSV files) ----
DB_FILENAME = "habits.db"     # lives in the data folder (data/habits.db by default)
HEARTBEAT_SECONDS = 10        # how often a running tracker marks itself as alive

# ---- active-window tracker (python -m backend.activity, or started by the server) ----
ACTIVITY_POLL_SECONDS = 2     # how often the focused window is checked
ACTIVITY_IDLE_SECONDS = 120   # no keyboard/mouse input this long counts as idle
ACTIVITY_STORE_TITLES = False # window titles can be private; only app, site and category are kept
DOOMSCROLL_CATEGORIES = ["social", "video"]   # time in these counts toward doomscrolling

# ---- analytics (patterns the assistant can look up) ----
STREAK_GAP_SECONDS = 120      # leaving an app for less than this doesn't end a session in it
STREAK_BUCKETS_MIN = [0, 15, 45, 90]   # "minutes into the current app session" buckets
MIN_EXPOSURE_MINUTES = 30     # ignore contexts you spent less time in than this
MIN_PATTERN_EVENTS = 5        # a pattern needs at least this many habit events
PATTERN_FDR = 0.10            # false discovery rate for find_patterns (Benjamini-Hochberg)

# ---- local LLM (Ollama) ----
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b-instruct"   # any Ollama model with tool calling works
LLM_MAX_TOOL_ROUNDS = 6
OLLAMA_KEEP_ALIVE = "30m"     # keep the model in memory between questions (Ollama's default unloads it after 5 min)
OLLAMA_NUM_CTX = 8192         # context window; big enough for the tool definitions plus a few tool results

# ---- nudges and the bandit ----
NUDGES_ENABLED = True
DOOMSCROLL_MINUTES = 20       # this long in a doomscroll category (with short breaks allowed) triggers a nudge
NUDGE_COOLDOWN_MINUTES = 10   # at most one nudge per trigger type in this time
NUDGE_GRACE_SECONDS = 60      # time to act on the nudge before it is judged
NUDGE_OUTCOME_MINUTES = 5     # success = no habit contact / doomscrolling from grace until here
NUDGE_RANDOM_FRACTION = 0.2   # share of nudges picked uniformly at random (the comparison group)
NUDGE_ARMS = {
    #"walk": "Take a 2-minute walk",
    #"fidget": "Grab a fidget toy or stress ball",
    "switch_task": "Switch to a different task for a few minutes",
    "water": "Get a glass of water",
    "breathe": "Do 5 slow breaths with your hands on the desk",
    "stretch": "Stretch your arms over your head and fix your posture",
    #"hands_busy": "Hold something in both hands (pen, mug, putty)",
    "close_tab": "Close this tab and write down what you came here for",
}
NUDGE_ARMS_BY_TRIGGER = {
    "habit": ["switch_task", "water", "breathe", "stretch", "hands_busy"],
    "doomscroll": ["switch_task", "water", "breathe", "stretch", "close_tab"],
}
