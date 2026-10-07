# 📤 How to Share Your API

This guide explains what to share with different types of users.

## 🎯 For Different Audiences

### Non-Technical Users (Managers, Clients)
**Share this link:**
```
https://geo-measurement-api.onrender.com
```
- They'll see a nice landing page
- Explains what the API does
- Shows it's running and healthy

---

### Developers / Testers
**Share this link:**
```
https://geo-measurement-api.onrender.com/docs
```

**What they can do:**
- Upload Shapefile, KML, or KMZ files
- See results immediately
- Test all endpoints in browser
- No coding required!

**Alternative - Full Documentation:**
- Repository: https://github.com/gousekareem/geo-measurement-api
- README has full API details

---

### Backend Developers / Integrations
**Share this:**
```
Base URL: https://geo-measurement-api.onrender.com
API Root: https://geo-measurement-api.onrender.com/api/files/
Docs: https://geo-measurement-api.onrender.com/docs
```

**Example cURL commands:**

1. **Upload a file:**
```bash
curl -X POST "https://geo-measurement-api.onrender.com/api/files/" \
  -F "file=@yourfile.kml"
```

2. **List files:**
```bash
curl "https://geo-measurement-api.onrender.com/api/files/"
```

3. **Get features:**
```bash
curl "https://geo-measurement-api.onrender.com/api/files/{file-id}/features/"
```

4. **Get measurements:**
```bash
curl "https://geo-measurement-api.onrender.com/api/files/{file-id}/measurements/"
```

---

## 📋 Share Different Versions

### Quick Share
**One Line:**
> "Test our geospatial API here: https://geo-measurement-api.onrender.com/docs"

### Detailed Share
**For Teams:**
```markdown
## 🌍 Geo Measurement API

Upload Shapefile, KML, or KMZ files to get accurate area and length measurements.

### Try It Now
https://geo-measurement-api.onrender.com/docs

### Key Features
- 📂 Support for Shapefile, KML, KMZ
- 📐 Accurate CRS-aware measurements
- 🛡️ Secure file processing
- 📊 Instant results

### Available Endpoints
- Upload: POST /api/files/
- List: GET /api/files/
- Features: GET /api/files/{id}/features/
- Measurements: GET /api/files/{id}/measurements/

### Documentation
https://github.com/gousekareem/geo-measurement-api
```

### For Email
```
Subject: Geo Measurement API - Try it Now

Hi,

I've deployed a geospatial file processing API that can:
- Upload Shapefile, KML, or KMZ files
- Calculate area and length measurements
- Handle CRS transformations automatically

Try it here: https://geo-measurement-api.onrender.com/docs

You can upload your own files and see results instantly!

Best,
[Your Name]
```

---

## ✅ What to Expect When Sharing

### Status
- **Current Status:** ✅ Live and Running
- **Uptime:** 24/7 (on Render free tier with occasional pauses)
- **Maintenance:** Oct 14, 2026, 1:00 AM UTC

### Performance
- **Response Time:** < 2 seconds (typical)
- **File Size Limit:** 50 MB
- **Database:** SQLite (stores uploads)

### File Support
| Format | Support | Notes |
|--------|---------|-------|
| Shapefile (.zip) | ✅ | Must include .shp, .shx, .dbf |
| KML | ✅ | Google Maps format |
| KMZ | ✅ | Zipped KML files |

---

## 🔒 Privacy & Security

- **Data Retention:** Files stored in database (can be deleted via API)
- **Public API:** No authentication (free to use)
- **Security:** ZIP-bomb protection, XML security hardening
- **CORS:** Enabled for cross-domain requests

---

## 💡 Example Workflow

1. **User opens:** https://geo-measurement-api.onrender.com/docs
2. **User uploads:** A Shapefile or KML file
3. **API processes:**
   - Reads the file
   - Detects coordinate reference system
   - Calculates area/length in meters
4. **User gets:**
   - File ID
   - Feature count
   - Measurements (area, perimeter, length)
5. **User can then:**
   - Download results
   - Query individual features
   - Delete the file

---

## 🆘 Support

If users encounter issues:

1. Check the Swagger UI error message
2. Verify file format (must be valid Shapefile/KML/KMZ)
3. Check file size (< 50 MB)
4. Refer to GitHub README for detailed documentation

---

## 📊 Usage Tracking

Currently, the API stores:
- Uploaded file metadata
- Processing status
- Extracted features
- Calculated measurements

Users can delete files anytime via the API.

---

For detailed API documentation, see [DEPLOYMENT.md](DEPLOYMENT.md)
