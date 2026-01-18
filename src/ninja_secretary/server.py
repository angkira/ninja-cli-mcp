
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel


app = FastAPI()

class Secretary(BaseModel):
    id: int
    name: str
    department: str
    email: str | None = None

# Sample data
secretaries = [
    Secretary(id=1, name="Alice Johnson", department="HR", email="alice@company.com"),
    Secretary(id=2, name="Bob Smith", department="Finance", email="bob@company.com"),
]

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/secretaries", response_model=list[Secretary])
def get_secretaries():
    return secretaries

@app.get("/secretaries/{secretary_id}", response_model=Secretary)
def get_secretary(secretary_id: int):
    for secretary in secretaries:
        if secretary.id == secretary_id:
            return secretary
    raise HTTPException(status_code=404, detail="Secretary not found")

@app.post("/secretaries", response_model=Secretary, status_code=status.HTTP_201_CREATED)
def create_secretary(secretary: Secretary):
    # Check if secretary already exists
    for existing_secretary in secretaries:
        if existing_secretary.id == secretary.id:
            raise HTTPException(status_code=400, detail="Secretary with this ID already exists")
    secretaries.append(secretary)
    return secretary

@app.put("/secretaries/{secretary_id}", response_model=Secretary)
def update_secretary(secretary_id: int, updated_secretary: Secretary):
    for i, secretary in enumerate(secretaries):
        if secretary.id == secretary_id:
            secretaries[i] = updated_secretary
            return updated_secretary
    raise HTTPException(status_code=404, detail="Secretary not found")

@app.delete("/secretaries/{secretary_id}")
def delete_secretary(secretary_id: int):
    for i, secretary in enumerate(secretaries):
        if secretary.id == secretary_id:
            del secretaries[i]
            return {"message": "Secretary deleted"}
    raise HTTPException(status_code=404, detail="Secretary not found")
