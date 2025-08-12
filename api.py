from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import httpx
from urllib.parse import urlparse
from pydantic import BaseModel
from typing import List, Optional
from config import settings
from main import process_keyword_search, get_actions_for_keyword, get_creators

app = FastAPI(
    title=settings.app_name, 
    version=settings.app_version,
    debug=settings.debug
)

# Allow CORS for local development UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"]
    ,
    allow_headers=["*"]
)

print(settings.openai_api_key)

class ActionResponse(BaseModel):
    action: str
    url: str
    comment: Optional[str] = None
    caption: Optional[str] = None
    img_url: Optional[str] = None

class KeywordRequest(BaseModel):
    keyword: str

# Generic actions for unknown keywords
GENERIC_ACTIONS = [
    {
      "action": 'follow',
      "url": 'https://instagram.com/fitness_guru_official',
      "img_url": 'https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg'
    },
    {
      "action": 'like',
      "url": "https://www.instagram.com/p/C8X10w6Pd3X/",
      "caption": "Full video 🔗in b!0 AsoebiBar provides an Online One-Stop-Shop for Asoebi; which is traditional Afri...",
      "img_url": "https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg"
    },
    {
      "action": 'comment',
      "url": 'https://www.instagram.com/p/BaY6cwuglzg/',
      "comment": "Great content! Keep it up! 👏",
    },
    {
      "action": 'follow',
      "url": 'https://instagram.com/healthy_lifestyle_tips',
      "img_url": 'https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg',
    },
    {
      "action": 'like',
      "img_url": 'https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg',
      "caption": "Excited to share my latest fitness journey update! 💪 Down 20lbs and feeling stronger than ever. Check out my workout tips and meal prep ideas below! #FitnessJourney #HealthyLifestyle",
      "url": 'https://www.instagram.com/p/cUQsS4EHgu/',
    },
]


@app.get("/")
async def root():
    return {"message": "Social Media Promotion API is running!"}

@app.post("/actions", response_model=List[ActionResponse])
async def get_actions(request: KeywordRequest):
    """
    Get a list of social media actions (follow, like, comment) for a given keyword
    """
    keyword = request.keyword.lower().strip()
    
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    try:
        # Generate real actions based on the keyword
        actions = await get_actions_for_keyword(keyword, max_posts=12)
        
        # If no actions found, return generic actions as fallback
        if not actions:
            return []
        
        return actions
        
    except Exception as e:
        # If there's an error, return generic actions as fallback
        print(f"Error getting actions for keyword '{keyword}': {str(e)}")
        return []

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is operational"}


class CreatorsRequest(BaseModel):
    keyword: str
    country: Optional[str] = None
    followers_count_gt: Optional[int] = None
    followers_count_lt: Optional[int] = None


@app.post("/creators")
async def get_creators_post_api(request: CreatorsRequest):
    """
    POST: Accepts JSON body with keyword, country and optional follower filters
    """
    keyword = (request.keyword or "").strip()
    country = (request.country or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    filters = {}
    if request.followers_count_gt is not None:
        filters["followers_count_gt"] = request.followers_count_gt
    if request.followers_count_lt is not None:
        filters["followers_count_lt"] = request.followers_count_lt
    if country:
        filters["country"] = country

    return await get_creators(keyword, filters)

@app.get("/proxy-image")
async def proxy_image(url: str):
    """
    Image proxy to bypass CDN CORS/CORP for profile pictures.
    Only allows known instagram/fb cdn hosts.
    """
    parsed = urlparse(url)
    allowed_hosts = (
        "instagram.com",
        "cdninstagram.com",
        "fbcdn.net",
    )
    if not any(host in parsed.netloc for host in allowed_hosts):
        raise HTTPException(status_code=400, detail="Host not allowed")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.instagram.com/",
        }) as client:
            r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Failed to fetch image")
        content_type = r.headers.get("Content-Type", "image/jpeg")
        headers = {
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        }
        return Response(content=r.content, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")