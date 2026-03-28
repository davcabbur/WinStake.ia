# 🚀 Cómo Iniciar el Dashboard Web de WinStake.ia

El Dashboard está compuesto por dos partes separadas que deben ejecutarse al mismo tiempo: el **Backend** (API y WebSockets de datos) y el **Frontend** (La interfaz web).

Debes abrir **dos terminales distintas** para iniciarlo.

---

### Paso 1: Iniciar el Backend (FastAPI)
El backend sirve los datos calculados desde la base de datos `winstake.db` y maneja las cuotas en vivo.

1. Abre una terminal y asegúrate de estar en la carpeta raíz (`WinStake.ia`).
2. Activa el entorno virtual si no está activado y ejecuta el script de inicio:
   ```bash
   .\venv\Scripts\python run_api.py
   ```
3. Deberías ver un mensaje como `Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`. ¡Déjalo ejecutándose!

---

### Paso 2: Iniciar el Frontend (Angular)
El frontend proporciona la interfaz visual y se conecta al puerto del backend.

1. Abre una **nueva** terminal (manteniendo abierta la del Paso 1).
2. Navega a la carpeta del frontend:
   ```bash
   cd frontend
   ```
3. Inicia el servidor de desarrollo de Angular:
   ```bash
   npm start
   ```
   *(Si es la primera vez o instalaste algo nuevo, recuerda ejecutar `npm install` antes).*
4. Te indicará que la aplicación está disponible en el navegador.

---

### Paso 3: Ver el Dashboard
Una vez que ambos servidores están corriendo sin errores:

👉 **Abre tu navegador y entra en:** [http://localhost:4200](http://localhost:4200)

*(Verás las métricas cargarse y el componente de Live Odds empezará a recibir actualizaciones automáticamente gracias al WebSocket conectado a `ws://localhost:8000`).*

---

> 🛑 **Importante:** Para detener cualquiera de los dos servidores, ve a su respectiva ventana de terminal y presiona `Ctrl + C`.
