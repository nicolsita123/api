from fastapi import FastAPI, HTTPException, Request
from basededatos import db
from faker import Faker
import random
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import bcrypt  # Biblioteca para el hashing
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import os
import asyncio

app = FastAPI()
faker = Faker()


# Configurar Jinja2 para buscar plantillas en la carpeta "Src"
templates = Jinja2Templates(directory=os.path.join(os.getcwd(), "Src"))
app.mount("/src", StaticFiles(directory="Src"), name="static")
app.mount("/dist", StaticFiles(directory="Dist"), name="static")
# Ruta para renderizar el HTML
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "message": "Hello, FastAPI!"})

# Colección de MongoDB
users_collection = db["users"]

# Función para hashear una contraseña
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

# Función para generar un usuario aleatorio
def generate_user():
    duration_options = {
        "1 hours": timedelta(hours=1),
        "1 days": timedelta(days=1),
        "1 mounths": timedelta(days=30),
    }
    duration_key = random.choice(list(duration_options.keys()))
    expiration_date = datetime.utcnow() + duration_options[duration_key]

    plain_password = faker.password(length=10)  # Contraseña en texto plano
    hashed_password = hash_password(plain_password)  # Contraseña hasheada

    user = {
        "name": faker.name(),
        "email": faker.email(),
        "password": hashed_password,  # Guardar la contraseña hasheada
        "age": random.randint(18, 80),
        "duration": duration_key,
        "role": random.choice(["user", "admin"]),
        "expiration_date": expiration_date.isoformat(),
        "plain_password": plain_password  # Opcional: solo para pruebas, elimina en producción
    }
    return user

@app.post("/generate_users/")
async def generate_users(count: int):
    if count > 100:
        raise HTTPException(status_code=400, detail="El máximo permitido es 1,000 usuarios.")

    current_count = await users_collection.count_documents({})
    if current_count + count > 100:
        raise HTTPException(
            status_code=400,
            detail=f"Solo puedes agregar {100 - current_count} usuarios para no exceder el límite de 1,000.",
        )

    users = [generate_user() for _ in range(count)]
    result = await users_collection.insert_many(users)
    return {"message": f"{len(result.inserted_ids)} usuarios creados correctamente."}

@app.get("/users/")
async def get_users(limit: int = 10, skip: int = 0):
    """
    Obtener usuarios desde la colección con paginación.
    - `limit`: Número máximo de usuarios a devolver.
    - `skip`: Número de usuarios a omitir.
    """
  
    cursor = users_collection.find().skip(skip).limit(limit)
    users = []
    async for user in cursor:
        user["_id"] = str(user["_id"])  # Convertir ObjectId a string
        expiration_date = datetime.fromisoformat(user["expiration_date"])
        remaining_time = expiration_date - datetime.utcnow()
        remaining_time_str = str(remaining_time).split(".")[0]  # Formato legible
        user["remaining_time"] = remaining_time_str
        users.append(user)
    return users


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))



@app.delete("/clear_users/")
async def clear_users():
    """
    Eliminar todos los usuarios de la colección.
    """
    result = await users_collection.delete_many({})
    return {"message": f"Se eliminaron {result.deleted_count} usuarios."}

@app.on_event("startup")
async def auto_generate_users():
    current_count = await users_collection.count_documents({})
    print(f"Usuarios actuales: {current_count}")  # Debug
    if current_count == 0:
        users_to_generate = 100
        users = [generate_user() for _ in range(users_to_generate)]
        result = await users_collection.insert_many(users)
        print(f"{len(result.inserted_ids)} usuarios generados automáticamente.")


async def delete_expired_users():
    while True:
        current_time = datetime.utcnow()
        result = await users_collection.delete_many({"expiration_date": {"$lt": current_time.isoformat()}})
        if result.deleted_count > 0:
            print(f"{result.deleted_count} usuarios expirados eliminados.")
        await asyncio.sleep(60)  # Ejecutar cada 60 segundos

# Tarea de fondo para eliminar usuarios expirados
@app.on_event("startup")
async def auto_generate_users():
    current_count = await users_collection.count_documents({})
    print(f"Usuarios actuales: {current_count}")  # Debug
    if current_count < 100:
        users_to_generate = 100 - current_count
        users = [generate_user() for _ in range(users_to_generate)]
        result = await users_collection.insert_many(users)
        print(f"{len(result.inserted_ids)} usuarios generados automáticamente para completar 100.")
    else:
        print("Ya hay 100 o más usuarios.")
class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/login")
async def login(request: LoginRequest):
    user = await users_collection.find_one({"email": request.email})
    if not user:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    
    # Verificar la contraseña
    if not verify_password(request.password, user["password"]):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    
    # Verificar si la cuenta ha expirado
    expiration_date = datetime.fromisoformat(user["expiration_date"])
    if expiration_date < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Cuenta expirada.")
    
    return {"message": "Inicio de sesión exitoso", "name": user["name"], "role": user["role"]}

@app.get("/total_users/")
async def total_users():
    count = await users_collection.count_documents({})
    return {"total_users": count}

@app.get("/total_roles/")
async def total_roles():
    admin_count = await users_collection.count_documents({"role": "admin"})
    user_count = await users_collection.count_documents({"role": "user"})
    return {"admin_count": admin_count, "user_count": user_count}

@app.get("/user_durations/")
async def user_durations():
    hours_count = await users_collection.count_documents({"duration": "1 hours"})
    days_count = await users_collection.count_documents({"duration": "1 days"})
    months_count = await users_collection.count_documents({"duration": "1 mounths"})
    return {
        "hours_count": hours_count,
        "days_count": days_count,
        "months_count": months_count
    }

@app.get("/user_ages/")
async def user_ages():
    pipeline = [
        {"$group": {"_id": "$age", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}  # Ordenar por edad ascendente
    ]
    age_distribution = await users_collection.aggregate(pipeline).to_list(length=None)
    return [{"age": item["_id"], "count": item["count"]} for item in age_distribution]

@app.on_event("startup")
async def startup_event():
    print("La aplicación ha iniciado.")

@app.on_event("shutdown")
async def shutdown_event():
    print("La aplicación se está cerrando.")