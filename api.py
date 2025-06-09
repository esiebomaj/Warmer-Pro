from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import random
from config import settings

app = FastAPI(
    title=settings.app_name, 
    version=settings.app_version,
    debug=settings.debug
)

print(settings.openai_api_key)

class ActionResponse(BaseModel):
    action: str
    url: str
    comment: Optional[str] = None

class KeywordRequest(BaseModel):
    keyword: str

# Dummy data for different keywords
DUMMY_ACTIONS = {
    "fitness": [
        {
            "action": "follow",
            "url": "https://instagram.com/fitness_guru_official"
        },
        {
            "action": "like", 
            "url": "https://www.instagram.com/p/BaY6cwuglzg/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/BaY6cwuglzg/",
            "comment": "Great workout tips! Keep inspiring us! 💪"
        },
        {
            "action": "follow",
            "url": "https://instagram.com/healthy_lifestyle_tips"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/cUQsS4EHgu/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/dRTuV5FIhv/",
            "comment": "This is exactly what I needed to see today! 🔥"
        }
    ],
    "startup": [
        {
            "action": "follow",
            "url": "https://instagram.com/startup_hustle_daily"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/CeF7ghI2kLm/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/CeF7ghI2kLm/",
            "comment": "Solid advice for early-stage founders! 🚀"
        },
        {
            "action": "follow",
            "url": "https://instagram.com/tech_entrepreneur_life"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/BdR8tuF3nPq/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/BeS9uvG4oQr/",
            "comment": "Love seeing innovative solutions like this! 💡"
        }
    ],
    "african startup": [
        {
            "action": "follow",
            "url": "https://instagram.com/african_tech_hub"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/CfG8hij3lMn/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/CfG8hij3lMn/",
            "comment": "Amazing to see African innovation taking center stage! 🌍"
        },
        {
            "action": "follow",
            "url": "https://instagram.com/lagos_startup_scene"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/BgT0uvH5pRs/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/BhU1vwI6qSt/",
            "comment": "The future of tech is definitely African! Keep pushing boundaries 🚀"
        }
    ],
    "health": [
        {
            "action": "follow",
            "url": "https://instagram.com/wellness_warrior_daily"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/CgH9ikj4mNo/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/CgH9ikj4mNo/",
            "comment": "Such valuable health insights! Thanks for sharing 🌱"
        },
        {
            "action": "follow",
            "url": "https://instagram.com/mindful_living_tips"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/BiV2wxJ7rTu/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/BjW3xyK8sTv/",
            "comment": "This approach to wellness is game-changing! 💚"
        }
    ],
    "tourism": [
        {
            "action": "follow",
            "url": "https://instagram.com/wanderlust_adventures"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/ChI0jkl5nOp/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/ChI0jkl5nOp/",
            "comment": "Absolutely breathtaking destination! Adding to my bucket list ✈️"
        },
        {
            "action": "follow",
            "url": "https://instagram.com/local_travel_gems"
        },
        {
            "action": "like",
            "url": "https://www.instagram.com/p/CkX4zyM9uWx/"
        },
        {
            "action": "comment",
            "url": "https://www.instagram.com/p/ClY5azN0vXy/",
            "comment": "Hidden gems like this are why I love exploring! 🗺️"
        }
    ]
}

# Generic actions for unknown keywords
GENERIC_ACTIONS = [
    {
        "action": "follow",
        "url": "https://instagram.com/trending_content_creator"
    },
    {
        "action": "like",
        "url": "https://www.instagram.com/p/CmZ6b0O1wYz/"
    },
    {
        "action": "comment",
        "url": "https://www.instagram.com/p/CmZ6b0O1wYz/",
        "comment": "Great content! Keep it up! 👏"
    },
    {
        "action": "follow",
        "url": "https://instagram.com/inspiration_daily"
    },
    {
        "action": "like",
        "url": "https://www.instagram.com/p/CnA7c1P2xZ0/"
    }
]

@app.get("/")
async def root():
    return {"message": "Social Media Promotion API is running!"}

@app.post("/actions", response_model=List[ActionResponse])
async def get_actions_for_keyword(request: KeywordRequest):
    """
    Get a list of social media actions (follow, like, comment) for a given keyword
    """
    keyword = request.keyword.lower().strip()
    
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    # Check if we have specific actions for this keyword
    actions = None
    
    # Match keyword to predefined actions
    for key in DUMMY_ACTIONS.keys():
        if key in keyword or keyword in key:
            actions = DUMMY_ACTIONS[key].copy()
            break
    
    # If no specific match, use generic actions
    if not actions:
        actions = GENERIC_ACTIONS.copy()
    
    # Randomize the order and potentially reduce the number of actions
    random.shuffle(actions)
    
    # Return 3-6 actions randomly
    num_actions = random.randint(3, min(6, len(actions)))
    selected_actions = actions[:num_actions]
    
    return selected_actions

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is operational"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=True
    )
