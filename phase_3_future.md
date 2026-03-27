# WinStake.ia - Fase 3 (Desarrollo Futuro)

Este documento detalla las tareas a realizar **otro día**, una vez que la Fase 2 (Core, API y Frontend básico) esté completa y estable.

## Objetivos de la Fase 3

### 1. Sistema de Pagos (Fiat Legal)
*   **Integración de Pasarelas:** Integrar Stripe o PayPal para manejar depósitos y retiros en Euros/Dólares, cumpliendo con la legalidad vigente de la DGOJ (cero mercado negro crypto).
*   **Gestor de Saldos:** Crear la lógica transaccional segura en PostgreSQL para evitar fallos de concurrencia al actualizar el saldo de los usuarios tras un depósito o retiro.
*   **Registro Contable (Audit Trails):** Crear una tabla en la base de datos exclusiva para auditoría financiera.

### 2. Verificación KYC de Usuarios
*   **Flujo Documental:** Construir el sistema en Angular donde el usuario suba su DNI/Pasaporte.
*   **Integración a 3eros:** Conectar el backend con un proveedor de KYC automatizado (como Onfido o SumSub) para verificar la identidad y confirmar el campo `is_kyc_verified` de la base de datos de forma automática.
*   **Bloqueo de Retiros:** Implementar middleware en Backend que prevenga cualquier intento de retiro a usuarios sin KYC válido.

### 3. WebSockets y Tiempo Real
*   **Notificaciones Push:** Avisar al cliente en la WebApp cuando el `Analyzer` encuentre una *Value Bet* en directo.
*   **Tablas Vivas (Live Odds):** Conectar el backend a las APIS de cuotas en streaming e inyectar esos datos al frontend Angular vía WebSockets para que el usuario nunca tenga que recargar la página.

### 4. Empaquetado Móvil (Opcional pero Recomendado)
*   **Configuración Capacitor:** Instalar Capacitor en el proyecto Angular para transformar la Web App en una aplicación nativa instalable en Android (.apk) e iOS, acercándonos al modelo de Bet365.
