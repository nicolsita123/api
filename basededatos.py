from motor.motor_asyncio import AsyncIOMotorClient

# URI de conexión a MongoDB
MONGO_URI = "mongodb://localhost:27017"  # Cambia si usas otro host/puerto
DB_NAME = "test"  # Nombre de tu base de datos

# Crear el cliente de MongoDB
client = AsyncIOMotorClient(MONGO_URI)

# Seleccionar la base de datos
db = client[DB_NAME]
