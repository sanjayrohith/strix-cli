# 🚀 How to Use Strix - Quick Start Guide

## ✅ Strix is Now Fixed and Ready!

All 11 issues have been fixed. Strix now generates **perfect Docker configs** automatically.

---

## 📋 Prerequisites

1. ✅ Docker Desktop installed and running
2. ✅ Python 3.13+ installed
3. ✅ Strix installed (`pip install -e .`)
4. ✅ GROQ_API_KEY in `.env` file

---

## 🎯 Usage: 3 Simple Steps

### Step 1: Run Strix on Any GitHub Repo

```bash
cd ~/path/to/strix-cli
python -m cli.main scan https://github.com/USERNAME/REPO --os linux
```

**Example:**
```bash
python -m cli.main scan https://github.com/sanjayrohith/ResQ-Desk --os linux
```

**Output:**
```
Starting analysis of repository: https://github.com/sanjayrohith/ResQ-Desk
Cloning...
Cloned successfully.
Detected languages: ['TypeScript', 'JavaScript']  Frameworks: ['Vite', 'React']
Generating artifacts via AI...
Validating and fixing generated artifacts...
Writing files to /tmp/strix_xxx/ResQ-Desk...
  wrote Dockerfile
  wrote docker-compose.dev.yml
  wrote docker-compose.yml
  wrote nginx.conf
  wrote .dockerignore
  wrote .env.example
  wrote PROJECT.md
Done! Check the output in: /tmp/strix_xxx/ResQ-Desk
```

---

### Step 2: Copy Files to Your Project

```bash
# Note the output directory from Step 1
cd /tmp/strix_xxx/ResQ-Desk

# Copy all Docker files
cp Dockerfile docker-compose.dev.yml docker-compose.yml nginx.conf .dockerignore ~/path/to/your/project/
```

**Or clone the repo first:**
```bash
# Clone the repo locally
git clone https://github.com/USERNAME/REPO.git
cd REPO

# Run Strix (it will generate files in /tmp)
python -m cli.main scan https://github.com/USERNAME/REPO --os linux

# Copy generated files here
cp /tmp/strix_xxx/REPO/* .
```

---

### Step 3: Build and Run

#### Option A: Docker Build (Simple)
```bash
cd ~/path/to/your/project

# Build the image
docker build -t myapp .

# Run the container
docker run -d -p 80:80 --name myapp myapp

# Visit http://localhost
open http://localhost

# Stop when done
docker stop myapp
docker rm myapp
```

#### Option B: Docker Compose (Recommended)

**Development Mode (Hot Reload):**
```bash
docker compose -f docker-compose.dev.yml up --build

# Visit http://localhost:5173
# Edit files and see changes instantly
# Stop with Ctrl+C
```

**Production Mode:**
```bash
docker compose -f docker-compose.yml up --build -d

# Visit http://localhost:80
# Runs in background with auto-restart
# Stop with: docker compose down
```

---

## 🧪 Testing Checklist

After running your container, verify:

### 1. App Loads
```bash
open http://localhost  # or http://localhost:5173 for dev
```
✅ Should see your app

### 2. SPA Routing Works
- Navigate to a route (e.g., `/about`)
- Refresh the page (Cmd + R)
- ✅ Should NOT get 404

### 3. Container is Healthy
```bash
docker ps
```
✅ Should show `(healthy)` status

### 4. No Errors in Logs
```bash
docker logs myapp
# or
docker compose logs
```
✅ Should see normal nginx access logs, no errors

---

## 🎯 What Strix Generates

### For React/Vite/Next.js Projects:

1. **Dockerfile** - Multi-stage build (Node builder + nginx runtime)
2. **docker-compose.dev.yml** - Development with hot-reload
3. **docker-compose.yml** - Production with auto-restart
4. **nginx.conf** - Perfect config with SPA routing, caching, compression
5. **.dockerignore** - Comprehensive exclusions
6. **.env.example** - Environment variable template
7. **PROJECT.md** - Documentation
8. **RUN_COMMANDS.sh** - Shell script for manual setup
9. **commands.json** - Machine-readable commands

---

## 🔧 Common Issues & Solutions

### Issue 1: "Docker is not running"
```bash
# Start Docker Desktop
open -a Docker

# Wait 30 seconds, then try again
docker ps
```

### Issue 2: "Port already in use"
```bash
# Find what's using the port
lsof -i :80

# Kill it or use a different port
docker run -p 8080:80 myapp
```

### Issue 3: "Cannot find module"
```bash
# Make sure you're in the right directory
cd ~/path/to/your/project

# Check if package.json exists
ls -la package.json

# Rebuild without cache
docker build --no-cache -t myapp .
```

### Issue 4: "404 on refresh"
This means nginx.conf is missing SPA routing. Strix now fixes this automatically, but if you see it:
```bash
# Regenerate with latest Strix
python -m cli.main scan YOUR_REPO_URL --os linux

# Copy the new nginx.conf
cp /tmp/strix_xxx/REPO/nginx.conf .

# Rebuild
docker build -t myapp .
```

---

## 📊 Success Indicators

You'll know Strix worked perfectly when:

✅ Build completes without errors
✅ Container starts and shows (healthy)
✅ App loads at http://localhost
✅ Refreshing on routes doesn't 404
✅ No redirect loops
✅ No manual fixes needed

---

## 🎓 Pro Tips

### Tip 1: Use Docker Compose
It's easier than raw docker commands:
```bash
docker compose up -d    # Start
docker compose logs -f  # Watch logs
docker compose down     # Stop
```

### Tip 2: Check Generated Files First
Before building, review:
```bash
cat Dockerfile
cat nginx.conf
cat docker-compose.yml
```

### Tip 3: Keep Strix Updated
```bash
cd ~/path/to/strix-cli
git pull  # If you cloned it
```

### Tip 4: Test Dev Mode First
Development mode is faster to iterate:
```bash
docker compose -f docker-compose.dev.yml up
# Make changes, see them instantly
```

---

## 🚀 Next Steps

1. ✅ Run Strix on your project
2. ✅ Copy generated files
3. ✅ Build and run with Docker
4. ✅ Test the app
5. ✅ Deploy to production!

---

## 📚 Additional Resources

- **Strix Documentation:** See `README.md`
- **Problem Analysis:** See `STRIX_PROBLEMS_ANALYSIS.md`
- **Validation Results:** See `AI_LEARNING_VALIDATION.md`
- **Before/After:** See `BEFORE_AFTER_COMPARISON.md`

---

## 🆘 Need Help?

If something doesn't work:
1. Check Docker is running: `docker ps`
2. Check the logs: `docker logs CONTAINER_NAME`
3. Verify files were generated: `ls -la /tmp/strix_xxx/REPO/`
4. Try rebuilding: `docker build --no-cache -t myapp .`

---

**Strix is ready to use! Generate perfect Docker configs for any React/Vite/Next.js project in seconds.**

🎉 Happy containerizing!
