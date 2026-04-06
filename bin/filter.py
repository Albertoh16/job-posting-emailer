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
ZSCORE_THRESHOLD = 0.5

# Minimum number of jobs required to compute a meaningful z-score.
ZSCORE_MIN_SAMPLES = 5

# Field groups for per-field query building.
TITLE_KEYS = ["job-titles", "position", "specialization"]
QUAL_KEYS = ["qualification"]
INDUSTRY_KEYS = ["industry"]

# ── Query builders ────────────────────────────────────────────────────────────

def buildFieldQuery(filters: dict, keys: list) -> str | None:
    terms = []
    for key in keys:
        terms.extend(filters.get(key, set()))
    return " ".join(terms) if terms else None

# ── Job text extractors ─────────────────────────────────────────────

def jobTitleText(title: str) -> str:
    return title.strip()

def jobQualText(qualifications: str) -> str:
    return qualifications.strip() if qualifications else ""

def jobIndustryText(industry: list) -> str:
    return ", ".join(industry) if industry else ""

# ── Scoring ───────────────────────────────────────────────────────────────────

def computeFieldScores(
    model,
    flatJobs: list,
    titleQuery: str | None,
    qualQuery: str | None,
    industryQuery: str | None,
) -> list[float]:

    n = len(flatJobs)

    # Encode query embeddings only for fields the user has set.
    titleEmb = model.encode(titleQuery, convert_to_tensor=True) if titleQuery    else None
    qualEmb = model.encode(qualQuery, convert_to_tensor=True) if qualQuery     else None
    industryEmb = model.encode(industryQuery, convert_to_tensor=True) if industryQuery else None

    activeFields = sum(e is not None for e in [titleEmb, qualEmb, industryEmb])

    if activeFields == 0:
        return [None] * n

    # Encode job fields in batch for each active embedding.
    titleTexts = [jobTitleText(j[1])    for j in flatJobs]
    qualTexts = [jobQualText(j[7])     for j in flatJobs]
    industryTexts = [jobIndustryText(j[5]) for j in flatJobs]

    titleJobEmbs = model.encode(titleTexts, convert_to_tensor=True, batch_size=64) if titleEmb    is not None else None
    qualJobEmbs = model.encode(qualTexts, convert_to_tensor=True, batch_size=64) if qualEmb     is not None else None
    industryJobEmbs = model.encode(industryTexts, convert_to_tensor=True, batch_size=64) if industryEmb is not None else None

    scores = []

    for i in range(n):
        fieldScores = []

        if titleEmb is not None:
            fieldScores.append(util.cos_sim(titleJobEmbs[i], titleEmb).item())

        if qualEmb is not None:
            fieldScores.append(util.cos_sim(qualJobEmbs[i], qualEmb).item())

        if industryEmb is not None:
            fieldScores.append(util.cos_sim(industryJobEmbs[i], industryEmb).item())

        scores.append(sum(fieldScores) / len(fieldScores))

    return scores

# Calculates a dynamic inclusion threshold using z-score normalization.
def computeZScoreThreshold(scores: list[float]) -> float:
    validScores = [s for s in scores if s is not None]

    if not validScores:
        return 0.0

    mean = sum(validScores) / len(validScores)

    if len(validScores) < ZSCORE_MIN_SAMPLES:
        print(f"[Filter] Too few samples ({len(validScores)}) for z-score, using mean cutoff ({mean:.3f}).")
        return mean

    variance = sum((s - mean) ** 2 for s in validScores) / len(validScores)
    std = variance ** 0.5
    threshold = mean + ZSCORE_THRESHOLD * std

    print(f"[Filter] Z-score threshold: mean={mean:.3f}, std={std:.3f}, cutoff={threshold:.3f}")

    return threshold

# ── Exclusion Checks ─────────────────────────────────────────────

def matchesAny(keywords: set, target: str) -> str | None:
    targetLower = target.lower()

    for keyword in keywords:
        if keyword.lower() in targetLower:
            return keyword
        
    return None

def excludeCheck(title: str, qualifications: str, industry: list, filters: dict) -> str | None:
    industryStr = ", ".join(industry) if industry else ""
    qualStr     = qualifications or ""

    titleKeywords = (
        filters.get("exclude position", set()) |
        filters.get("exclude specialization", set())
    )

    matched = matchesAny(titleKeywords, title)

    if matched:
        return f"title:'{matched}'"

    matched = matchesAny(filters.get("exclude qualification", set()), qualStr)

    if matched:
        return f"qualification:'{matched}'"

    matched = matchesAny(filters.get("exclude industry", set()), industryStr)

    if matched:
        return f"industry:'{matched}'"

    return None

# ── Location and work-model check ──────────────────────────────────

def countryCheck(location: str, filters: dict) -> bool:
    country = filters.get("country", "")
    if not country:
        return True
    return country.lower() in location.lower()

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

    # Builds per-field queries.
    titleQuery = buildFieldQuery(filters, TITLE_KEYS)
    qualQuery = buildFieldQuery(filters, QUAL_KEYS)
    industryQuery = buildFieldQuery(filters, INDUSTRY_KEYS)

    hasIncludeFilters = any([titleQuery, qualQuery, industryQuery])

    # Flattens jobs for batch processing.
    flatJobs: list = []

    for company, listings in resolvedJobs.items():
        for (title, url, location, workModel, industry, postDate, qualifications) in listings:
            flatJobs.append((company, title, url, location, workModel, industry, postDate, qualifications))

    if not flatJobs:
        return {}

    # ── Inclusion Score Calculation ──────────────────────────────────────────────

    scores = [None] * len(flatJobs)

    if hasIncludeFilters and model is not None:
        print(f"[Filter] Encoding {len(flatJobs)} jobs across {sum(q is not None for q in [titleQuery, qualQuery, industryQuery])} active field(s)...")
        scores = computeFieldScores(model, flatJobs, titleQuery, qualQuery, industryQuery)
        print(f"[Filter] Scoring jobs...")

    # Computes z-score threshold from this user's score distribution.
    threshold = computeZScoreThreshold(scores) if hasIncludeFilters and model is not None else None

    # ── Apply filters ─────────────────────────────────────────────────────────

    userJobs: dict[str, list] = {}

    for i, job in enumerate(flatJobs):
        company, title, url, location, workModel, industry, postDate, qualifications = job

        # Country filter.
        if not countryCheck(location, filters):
            print(f"[EXCLUDED] '{title}', location '{location}' not in country '{filters.get('country')}'")
            continue

        # Work-model filter.
        if not workModelCheck(workModel, filters):
            print(f"[EXCLUDED] '{title}', work model '{workModel}' not in {filters.get('work-model')}")
            continue

        # Substring exclusion across title, qualifications, and industry.
        excludeMatch = excludeCheck(title, qualifications, industry, filters)

        if excludeMatch:
            print(f"[EXCLUDED] '{title}', matched {excludeMatch}")
            continue

        # ML inclusion check.
        score = scores[i]

        if threshold is not None and score is not None:
            if score < threshold:
                print(f"[SKIPPED]  '{title}', score {score:.3f} < threshold {threshold:.3f}")
                continue

            print(f"[PASS]     '{title}', score {score:.3f} >= threshold {threshold:.3f}")

        elif score is None:
            print(f"[PASS]     '{title}', no include filters")

        if company not in userJobs:
            userJobs[company] = []

        userJobs[company].append((title, url, location, workModel, industry, postDate, qualifications))

    # Returns a sorted by most recent posting per company.
    return dict(
        sorted(userJobs.items(), key=lambda x: max(j[5] for j in x[1]), reverse=True)
    ) if userJobs else {}