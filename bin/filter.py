from sentence_transformers import util
import torch

# Model is loaded lazily, only when FilterJobs is first called.
# This means importing filter.py has no cost.
MODEL = None

def getModel():
    global MODEL

    if MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("[Filter] Loading sentence-transformer model...")
            MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            print("[Filter] Model loaded.")
            
        except Exception as e:
            print(f"[Filter] WARNING: Failed to load model: {e}. Will fall back to keyword-only filtering.")
            MODEL = None

    return MODEL

# How many standard deviations above the mean a job must score to pass.
ZSCORE_THRESHOLD = 0.7

# Minimum number of jobs required to compute a meaningful z-score.
ZSCORE_MIN_SAMPLES = 5

# ── Scoring (title only) ──────────────────────────────────────────────────────

def computeTitleScores(model, flatJobs: list, titleQuery: str) -> list[float]:
    titleTexts = [job[1].strip() for job in flatJobs]
    queryEmb   = model.encode(titleQuery, convert_to_tensor=True)
    jobEmbs    = model.encode(titleTexts, convert_to_tensor=True, batch_size=64)

    return [util.cos_sim(jobEmbs[i], queryEmb).item() for i in range(len(flatJobs))]

# Calculates a dynamic inclusion threshold using z-score normalization.
def computeZScoreThreshold(scores: list[float]) -> float:
    if not scores:
        return 0.0

    mean = sum(scores) / len(scores)

    if len(scores) < ZSCORE_MIN_SAMPLES:
        print(f"[Filter] Too few samples ({len(scores)}) for z-score, using mean cutoff ({mean:.3f}).")
        return mean

    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std      = variance ** 0.5
    threshold = mean + ZSCORE_THRESHOLD * std

    print(f"[Filter] Z-score threshold: mean={mean:.3f}, std={std:.3f}, cutoff={threshold:.3f}")

    return threshold

# ── Hard include checks ───────────────────────────────────────────────────────

def matchesAny(keywords: set, target: str) -> bool:
    targetLower = target.lower()
    return any(kw.lower() in targetLower for kw in keywords)

# Returns True if the job passes all active include filters.
# A filter only applies if the user actually set keywords for it.
def includeChecks(title: str, qualifications: str, industry: list, filters: dict) -> bool:
    specialization = filters.get("specialization", set())
    qualification  = filters.get("qualification", set())
    industryFilter = filters.get("industry", set())

    qualStr     = qualifications or ""
    industryStr = ", ".join(industry) if industry else ""

    # Specialization: must appear in the job title.
    if specialization and not matchesAny(specialization, title):
        print(f"[EXCLUDED] '{title}', no specialization match in {specialization}")
        return False

    # Qualification: must appear in the qualifications text.
    if qualification and not matchesAny(qualification, qualStr):
        print(f"[EXCLUDED] '{title}', no qualification match in {qualification}")
        return False

    # Industry: must appear in the industry list.
    if industryFilter and not matchesAny(industryFilter, industryStr):
        print(f"[EXCLUDED] '{title}', no industry match in {industryFilter}")
        return False

    return True

# Keywords to match in job titles for each hierarchy level.
HIERARCHY_KEYWORDS = {
    "intern":    ["intern"],
    "co-op":     ["co-op", "coop", "co op"],
    "new grad":  ["new grad", "new graduate", "entry level", "early career"],
    "junior":    ["junior", "jr.", "jr "],
    "senior":    ["senior", "sr.", "sr "],
}

def hierarchyCheck(title: str, filters: dict) -> bool:
    """Returns True only if the title matches one of the user's selected hierarchy levels.
    If no hierarchy is selected, no jobs pass."""
    allowed = filters.get("hierarchy", set())

    if not allowed:
        return False

    titleLower = title.lower()

    for level in allowed:
        for keyword in HIERARCHY_KEYWORDS.get(level, []):
            if keyword in titleLower:
                return True

    return False

# ── Work-model check ──────────────────────────────────────────────────────────

def workModelCheck(workModel: str, filters: dict) -> bool:
    allowed = filters.get("work-model", set())
    if not allowed:
        return True
    return workModel.lower() in {m.lower() for m in allowed}

# ── Main entry point ──────────────────────────────────────────────────────────

def FilterJobs(filters: dict, resolvedJobs: dict) -> dict:
    if not resolvedJobs:
        return {}

    model = getModel()

    # Build title query from job-title filter keywords.
    titleTerms = list(filters.get("job-title", set()))
    titleQuery = " ".join(titleTerms) if titleTerms else None

    # Flatten jobs for batch processing.
    flatJobs: list = []

    for company, listings in resolvedJobs.items():
        for (title, url, location, workModel, industry, postDate, qualifications) in listings:
            flatJobs.append((company, title, url, location, workModel, industry, postDate, qualifications))

    if not flatJobs:
        return {}

    # ── ML title scoring ──────────────────────────────────────────────────────

    scores    = [None] * len(flatJobs)
    threshold = None

    if titleQuery and model is not None:
        print(f"[Filter] Encoding {len(flatJobs)} job titles against query: '{titleQuery}'")
        scores    = computeTitleScores(model, flatJobs, titleQuery)
        threshold = computeZScoreThreshold(scores)

    # ── Apply filters ─────────────────────────────────────────────────────────

    userJobs: dict[str, list] = {}

    for i, job in enumerate(flatJobs):
        company, title, url, location, workModel, industry, postDate, qualifications = job

        # Hard check: work model.
        if not workModelCheck(workModel, filters):
            print(f"[EXCLUDED] '{title}', work model '{workModel}' not in {filters.get('work-model')}")
            continue

        # Hard check: hierarchy.
        if not hierarchyCheck(title, filters):
            print(f"[EXCLUDED] '{title}', matches no selected hierarchy {filters.get('hierarchy')}")
            continue

        # Hard checks: specialization, qualification, industry.
        if not includeChecks(title, qualifications, industry, filters):
            continue

        # ML title check.
        score = scores[i]

        if threshold is not None and score is not None:
            if score < threshold:
                print(f"[SKIPPED]  '{title}', score {score:.3f} < threshold {threshold:.3f}")
                continue
            print(f"[PASS]     '{title}', score {score:.3f} >= threshold {threshold:.3f}")
        else:
            print(f"[PASS]     '{title}', no title filter")

        if company not in userJobs:
            userJobs[company] = []

        userJobs[company].append((title, url, location, workModel, industry, postDate, qualifications))

    # Sort by most recent posting per company.
    return dict(
        sorted(userJobs.items(), key=lambda x: max(j[5] for j in x[1]), reverse=True)
    ) if userJobs else {}