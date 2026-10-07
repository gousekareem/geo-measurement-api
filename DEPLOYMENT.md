# 🚀 Deployment Guide

This document describes how the Geo Measurement API is deployed on Render.

## Deployed Application

**URL:** https://geo-measurement-api.onrender.com

## What's Available

### 🏠 Landing Page
- **URL:** https://geo-measurement-api.onrender.com
- **What:** Professional landing page with API overview and links
- **Audience:** Non-technical users, general visitors

### 📖 API Documentation (Swagger UI)
- **URL:** https://geo-measurement-api.onrender.com/docs
- **What:** Interactive API documentation where you can test endpoints
- **Audience:** Developers, API testers
- **Features:**
  - Upload files (Shapefile, KML, KMZ)
  - List uploaded files
  - View features and measurements
  - Try endpoints directly in browser

### ⚙️ API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/files/` | Upload and process file |
| GET | `/api/files/` | List uploaded files |
| GET | `/api/files/{id}/` | Get file information |
| GET | `/api/files/{id}/features/` | Get features data |
| GET | `/api/files/{id}/measurements/` | Get measurements |
| DELETE | `/api/files/{id}/` | Delete file |
| GET | `/health` | Health check |

### 🔗 Quick Links to Share

**For Testing in Browser:**
```
https://geo-measurement-api.onrender.com/docs
```

**For API Integration:**
```
https://geo-measurement-api.onrender.com/api/files/
```

**For Monitoring:**
```
https://geo-measurement-api.onrender.com/health
```

## How to Use

### 1. Upload a File (via Swagger UI)
1. Go to https://geo-measurement-api.onrender.com/docs
2. Find the `POST /api/files/` endpoint
3. Click "Try it out"
4. Upload a `.zip` (Shapefile), `.kml`, or `.kmz` file
5. Click "Execute"
6. You'll get a file ID and processing status

### 2. View Features
```bash
curl https://geo-measurement-api.onrender.com/api/files/{file-id}/features/
```

### 3. View Measurements
```bash
curl https://geo-measurement-api.onrender.com/api/files/{file-id}/measurements/
```

## Deployment Configuration

See `render.yaml` for Render-specific configuration:
- **Language:** Python 3.11
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT`
- **Database:** SQLite (can be switched to PostgreSQL)
- **Region:** Oregon (US West)

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `PYTHON_VERSION` | 3.11.0 | Python runtime version |
| `DATABASE_URL` | sqlite:///./geofiles.db | Database connection |
| `MAX_UPLOAD_MB` | 50 | Max upload size in MB |
| `MAX_UNCOMPRESSED_MB` | 200 | Max uncompressed archive size |
| `MAX_FEATURES` | 100000 | Max features per file |

## Testing the Deployment

### Health Check
```bash
curl https://geo-measurement-api.onrender.com/health
# Response: {"status":"ok"}
```

### Landing Page
```bash
curl https://geo-measurement-api.onrender.com
# Response: HTML landing page
```

### API Root
```bash
curl https://geo-measurement-api.onrender.com/api/files/
# Response: Empty file list JSON
```

## Troubleshooting

### Application won't start
- Check Render logs in dashboard
- Verify `requirements.txt` has all dependencies
- Ensure Python version is 3.11+

### Upload fails
- Check file size against `MAX_UPLOAD_MB`
- Verify file format (`.zip`, `.kml`, `.kmz`)
- Check Render logs for specific error

### Database errors
- Verify `DATABASE_URL` environment variable
- For production, switch to PostgreSQL
- Check file permissions on Render

## Production Recommendations

For production deployment:

1. **Use PostgreSQL instead of SQLite**
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/db
   ```

2. **Use a paid Render plan** (currently on free tier)
   - Free tier has limited resources
   - Recommended: 0.5 CPU, 512 MB RAM ($7/month)

3. **Enable auto-scaling** (paid plans)
   - Handles traffic spikes

4. **Add error tracking** (e.g., Sentry)
   - Monitor production issues

5. **Use a custom domain**
   - https://your-domain.com instead of onrender.com

## Deployment History

- **Initial Deployment:** Oct 7, 2026
- **Landing Page Added:** Oct 7, 2026
- **Status:** ✅ Active and Running

---

For more information, see [README.md](README.md)
