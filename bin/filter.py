from sentence_transformers import SentenceTransformer, util
import torch

# We load the module once to be reused across all users in a single run.
print("[mlFilter] Loading sentence-transformer model...")

MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

print("[mlFilter] Model loaded.")

# A job must score >= INCLUDE_THRESHOLD against the user's include intent to pass.
INCLUDE_THRESHOLD = 0.25

# A job must score >= EXCLUDE_THRESHOLD against any exclude keyword to be blocked.
EXCLUDE_THRESHOLD = 0.45

# Concatenates job fields into a single string for embedding.
def buildJobText(title: str, qualifications: str, industry: list) -> str:
    # We convert our list of industries into a string.
    industryStr = ", ".join(industry) if industry else ""

    # We clean all of the information and flatten it into a singular linear list.
    parts = [p for p in [title, qualifications, industryStr] if p and p.strip()]

    return " | ".join(parts)

# Collapses all include-side filter keywords into one natural language query.
# Returns None if no include filters are set, meaning the user wants everything.
def buildIncludeQuery(filters: dict) -> str | None:
    # List of the include column headers.
    keys = ["position", "role", "specialization", "qualification", "industry"]
    terms = []

    # We then add all the filters into a singular flattened list.
    for key in keys:
        terms.extend(filters.get(key, set()))

    return " ".join(terms) if terms else None

# Returns a list of exclude strings, one per filter category that has values.
# We keep them separate so a strong match on any exclude category blocks the job.
def buildExcludeQueries(filters: dict) -> list[str]:
    # List of the exclude column headers.
    keys = [
        "exclude position",
        "exclude role",
        "exclude specialization",
        "exclude qualification",
        "exclude industry",
    ]

    queries = []
    
    # We go through all the keys and append them to our queries.
    for key in keys:
        terms = filters.get(key, set())
    
        if terms:
            queries.append(" ".join(terms))
    
    return queries

# We utilize the sentance-tranformer ML for semantic similarity scoring.
# Returns a dict in the same structure as resolvedJobs, sorted by most recent post.
def FilterJobs(filters: dict, resolvedJobs: dict) -> dict:
    if not resolvedJobs:
        return {}

    # We build query embeddings for our inclusion and exclusion filterings.
    includeQuery = buildIncludeQuery(filters)
    excludeQueries = buildExcludeQueries(filters)

    # We convert our flattened filters into embeddings in order to later
    # compare similarity scoring with the list of jobs that will be sent in. 
    includeEmbedding = MODEL.encode(includeQuery, convert_to_tensor=True) if includeQuery else None
    excludeEmbeddings = MODEL.encode(excludeQueries, convert_to_tensor=True) if excludeQueries else None

    # Flattens all jobs and builds their text blobs
    # We batch-encode everything at once for speed.
    
    # (company, title, url, location, workModel, industry, postDate, qualifications)
    flatJobs  = [] 
    jobTexts  = []

    # We populate the list of all flattened job posting information.
    for company, listings in resolvedJobs.items():
        for (title, url, location, workModel, industry, postDate, qualifications) in listings:
            flatJobs.append((company, title, url, location, workModel, industry, postDate, qualifications))
            jobTexts.append(buildJobText(title, qualifications, industry))

    # If we don't have any flatened jobs, we cannot continue and return nothing.
    if not flatJobs:
        return {}

    print(f"[mlFilter] Encoding {len(jobTexts)} jobs...")

    # We then create an embedding for job postings for comparisons
    # with the user's inclusion/exclusion filtering embeddings. 
    jobEmbeddings = MODEL.encode(jobTexts, convert_to_tensor=True, batch_size=64)

    print(f"[mlFilter] Scoring jobs...")

    userJobs: dict[str, list] = {}

    for i, job in enumerate(flatJobs):
        company, title, url, location, workModel, industry, postDate, qualifications = job
        jobEmb = jobEmbeddings[i]

        # Blocks if too similar to any exclude cluster.
        if excludeEmbeddings is not None:
            excludeScores = util.cos_sim(jobEmb, excludeEmbeddings)[0] 
            
            if torch.any(excludeScores >= EXCLUDE_THRESHOLD):
                topExclude = excludeScores.max().item()
                print(f"[EXCLUDED] '{title}' — exclude score {topExclude:.3f}")
                continue

        # Includes similarity check.
        if includeEmbedding is not None:
            score = util.cos_sim(jobEmb, includeEmbedding).item()

            if score < INCLUDE_THRESHOLD:
                print(f"[SKIPPED]'{title}' include score {score:.3f}")
                continue

            print(f"[PASS]'{title}' score {score:.3f}")

        else:
            # No included filters everything that survived exclude passes.
            print(f" [PASS]'{title}' no include filters")

        # We'll create a key pairing if the job does not appear in the job-to-posting map.
        if company not in userJobs:
            userJobs[company] = []

        # We'll recreate the list of job postings now with the filtering done.
        userJobs[company].append((title, url, location, workModel, industry, postDate, qualifications))

    # Returns a sorted list of companies by their most recent posting, same as before.
    return dict(
        sorted(userJobs.items(), key=lambda x: max(j[5] for j in x[1]), reverse=True)
    ) if userJobs else {}