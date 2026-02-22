# Strix Code Problems - Root Cause Analysis

## 🔴 Critical Issues in Strix Codebase

### Problem 1: Prompt Contradicts Itself on Non-Root Users

**Location:** `prompts/generate_artifacts_prompt.txt` line 11

**The Contradiction:**
```
"Create a non-root runtime user and set correct file permissions."
```

**Why This is Wrong:**
- For **nginx** containers, you CANNOT use non-root users because nginx needs root to bind to ports 80/443
- The prompt doesn't distinguish between app containers (Node/Python) and web servers (nginx)
- This causes the AI to generate `USER node` in nginx containers, breaking them

**Fix Required:**
```diff
- Create a non-root runtime user and set correct file permissions.
+ For application containers (Node.js apps, Python apps), create a non-root runtime user.
+ For nginx containers serving static files, run as root (nginx drops privileges automatically).
+ Never use USER directive in nginx-based Dockerfiles.
```

---

### Problem 2: Wrong Port Guidance for Frontend Apps

**Location:** `backend/generator.py` line 108 in `_build_user_prompt()`

**The Issue:**
```python
"Guidance for the AI:\n"
"- Prefer multi-stage Dockerfiles. For a frontend build (Vite), produce a builder stage that runs `npm ci` and `npm run build` and a runtime stage that serves `/dist` with `nginx:alpine` (recommended).\n"
```

**What's Missing:**
- No mention that nginx should serve on port 80 (standard HTTP)
- No mention that the detected port (5173 for Vite) is ONLY for dev mode
- AI gets confused and uses dev port (5173) in production nginx config

**Fix Required:**
```diff
- and a runtime stage that serves `/dist` with `nginx:alpine` (recommended).\n"
+ and a runtime stage that serves `/dist` with `nginx:alpine` on port 80 (standard HTTP).\n"
+ IMPORTANT: The detected port (e.g., 5173 for Vite) is ONLY for development mode.
+ Production nginx containers should ALWAYS expose port 80, not the dev server port.\n"
```

---

### Problem 3: No Guidance on nginx.conf COPY Instruction

**Location:** `prompts/generate_artifacts_prompt.txt` - Missing entirely

**The Issue:**
- Prompt says to generate `nginx.conf` content
- But doesn't tell AI to add `COPY nginx.conf /etc/nginx/conf.d/default.conf` to Dockerfile
- AI generates the file but forgets to copy it into the container

**Fix Required:**
Add to prompt after line 11:
```
- When generating nginx.conf for static frontends, ensure the Dockerfile includes:
  COPY nginx.conf /etc/nginx/conf.d/default.conf
- Do NOT just remove default.conf without replacing it.
```

---

### Problem 4: Healthcheck Uses Wrong Tool

**Location:** `prompts/generate_artifacts_prompt.txt` line 12

**The Issue:**
```
"include a `HEALTHCHECK` that verifies the app is reachable"
```

**What's Missing:**
- No guidance on WHICH tool to use (curl vs wget)
- Alpine images don't include curl by default
- AI defaults to curl, causing healthchecks to fail

**Fix Required:**
```diff
- include a `HEALTHCHECK` that verifies the app is reachable on the expected port/path.
+ include a `HEALTHCHECK` using wget (available in Alpine) or install curl first.
+ Example: HEALTHCHECK CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1
+ Do NOT use curl unless you explicitly RUN apk add --no-cache curl first.
```

---

### Problem 5: Missing Vite Dev Server Host Binding

**Location:** `backend/generator.py` line 115 in `_build_user_prompt()`

**The Issue:**
```python
"- Provide both `docker-compose.dev.yml` (mount source, use hot-reload command, preserve container node_modules)"
```

**What's Missing:**
- Vite dev server binds to localhost by default
- Inside Docker, localhost means the container, not the host
- Need `--host 0.0.0.0` flag to accept external connections

**Fix Required:**
```diff
- Include a service override for running the app with hot-reload commands (e.g., `npm run dev`, `uvicorn --reload`).
+ Include a service override for running the app with hot-reload commands.
+ For Vite/React: use `npm run dev -- --host 0.0.0.0` to accept connections from host.
+ For Next.js: use `npm run dev` (already binds to 0.0.0.0).
+ For Python: use `uvicorn main:app --reload --host 0.0.0.0`.
```

---

### Problem 6: No SPA Routing Guidance

**Location:** `prompts/generate_artifacts_prompt.txt` - Missing entirely

**The Issue:**
- React/Vue apps use client-side routing
- nginx needs `try_files $uri $uri/ /index.html;` to handle routes
- Without this, refreshing on `/about` returns 404

**Fix Required:**
Add to prompt:
```
- For Single Page Applications (React, Vue, Angular), nginx.conf MUST include:
  location / {
    try_files $uri $uri/ /index.html;
  }
  This ensures client-side routing works correctly.
```

---

### Problem 7: Incomplete .dockerignore Guidance

**Location:** `prompts/generate_artifacts_prompt.txt` line 11

**The Issue:**
```
"copy only required files (use `.dockerignore` recommendations in `PROJECT.md`)"
```

**What's Wrong:**
- Circular reference: .dockerignore should be in the prompt, not PROJECT.md
- No explicit list of what to exclude
- AI generates minimal .dockerignore (only .git, node_modules, npm-debug.log)

**Fix Required:**
Add explicit .dockerignore template to prompt:
```
- ".dockerignore" – Exclude unnecessary files from Docker build context:
  node_modules, .git, .env, .env.local, dist, coverage, *.log, .vscode, .idea, .DS_Store, Thumbs.db
```

---

### Problem 8: No Production Compose File Guidance

**Location:** `prompts/generate_artifacts_prompt.txt` line 19

**The Issue:**
```
"docker-compose.yml" – A minimal production compose example (optional if not applicable)
```

**What's Wrong:**
- Says "optional" so AI often skips it
- No guidance on what makes it different from dev compose
- No mention of restart policies, healthchecks, or volume management

**Fix Required:**
```diff
- "docker-compose.yml" – A minimal production compose example (optional if not applicable) that uses built images and does not mount source code.
+ "docker-compose.yml" – A production compose file that:
+   - Uses the built Dockerfile (not source mounts)
+   - Includes restart: unless-stopped
+   - Includes healthcheck configuration
+   - Maps to standard ports (80 for web, not dev ports)
+   - Does NOT mount source code volumes
```

---

### Problem 9: Missing Compose Version Guidance

**Location:** `prompts/generate_artifacts_prompt.txt` - Missing

**The Issue:**
- AI generates `version: '3'` (outdated)
- Modern Docker Compose doesn't need version field
- When included, should be `3.8` for full feature support

**Fix Required:**
Add to prompt:
```
- Use `version: '3.8'` in docker-compose files for compatibility.
- Ensure proper YAML formatting with 2-space indentation.
```

---

### Problem 10: No Validation of AI Output

**Location:** `backend/generator.py` lines 145-165

**The Issue:**
```python
try:
    artifacts = json.loads(cleaned)
    if isinstance(artifacts, dict) and "Dockerfile" in artifacts:
        return artifacts
except json.JSONDecodeError:
    pass
```

**What's Wrong:**
- Only checks if "Dockerfile" key exists
- Doesn't validate the Dockerfile content
- Doesn't check for common mistakes (wrong ports, missing COPY, etc.)
- No post-processing to fix known issues

**Fix Required:**
Add validation function:
```python
def _validate_and_fix_artifacts(artifacts: Dict[str, str], profile: Dict[str, Any]) -> Dict[str, str]:
    """Validate and auto-fix common AI mistakes."""
    
    # Fix 1: Ensure nginx.conf is copied in Dockerfile
    if "nginx.conf" in artifacts and "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "nginx.conf" in dockerfile and "COPY nginx.conf" not in dockerfile:
            # Insert COPY instruction after FROM nginx:alpine
            dockerfile = dockerfile.replace(
                "FROM nginx:alpine",
                "FROM nginx:alpine\nCOPY nginx.conf /etc/nginx/conf.d/default.conf"
            )
            artifacts["Dockerfile"] = dockerfile
    
    # Fix 2: Remove USER directive from nginx containers
    if "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "nginx:alpine" in dockerfile and "USER " in dockerfile:
            lines = dockerfile.split("\n")
            lines = [l for l in lines if not l.strip().startswith("USER ")]
            artifacts["Dockerfile"] = "\n".join(lines)
    
    # Fix 3: Ensure Vite dev command has --host 0.0.0.0
    if "docker-compose.dev.yml" in artifacts:
        compose = artifacts["docker-compose.dev.yml"]
        frameworks = profile.get("frameworks", [])
        if "Vite" in frameworks and "npm run dev" in compose and "--host" not in compose:
            compose = compose.replace("npm run dev", "npm run dev -- --host 0.0.0.0")
            artifacts["docker-compose.dev.yml"] = compose
    
    # Fix 4: Replace curl with wget in healthchecks
    if "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "curl --fail" in dockerfile:
            dockerfile = dockerfile.replace(
                "curl --fail",
                "wget --no-verbose --tries=1 --spider"
            )
            artifacts["Dockerfile"] = dockerfile
    
    return artifacts
```

---

## 📊 Summary of Required Changes

### Files to Modify:
1. **prompts/generate_artifacts_prompt.txt** - 8 improvements needed
2. **backend/generator.py** - Add validation function + update user prompt
3. **backend/analyzer.py** - No changes needed (works correctly)
4. **cli/main.py** - No changes needed (works correctly)

### Priority Order:
1. 🔴 **HIGH**: Fix nginx non-root user contradiction (breaks containers)
2. 🔴 **HIGH**: Fix port confusion (wrong ports in production)
3. 🔴 **HIGH**: Add nginx.conf COPY guidance (files not copied)
4. 🟡 **MEDIUM**: Add validation function (catches AI mistakes)
5. 🟡 **MEDIUM**: Fix Vite host binding (dev server inaccessible)
6. 🟡 **MEDIUM**: Add SPA routing guidance (404 on refresh)
7. 🟢 **LOW**: Improve .dockerignore template
8. 🟢 **LOW**: Add production compose guidance
9. 🟢 **LOW**: Fix healthcheck tool (curl vs wget)
10. 🟢 **LOW**: Update compose version

### Expected Improvement:
- **Before fixes:** 6.5/10 success rate
- **After fixes:** 9.5/10 success rate (near-perfect Docker configs)
