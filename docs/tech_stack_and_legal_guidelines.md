# Arquitectura, Base de Datos y Marco Legal (España / UE)

Este documento define las recomendaciones finales para la base de datos de WinStake.ia y detalla las estrictas consideraciones legales ("los peros") requeridas para operar en España y la Unión Europea sin infringir la ley.

## 1. Selección de Base de Datos: La Opción Más Segura

Para una aplicación que maneja retiros, pagos con criptomonedas y mecánicas de juego, la integridad de los datos financieros es crítica. **Ninguna base de datos es segura por defecto sin una configuración adecuada**, pero la arquitectura recomendada es:

### Recomendación Principal: PostgreSQL
*   **Por qué:** Es el estándar maduro y de código abierto para sistemas transaccionales pesados. Tiene cumplimiento total ACID (garantiza que las transacciones financieras no se corrompan).
*   **Seguridad:** Soporta encriptación en reposo (Transparent Data Encryption mediante herramientas o nivel de disco) y en tránsito (SSL/TLS). Permite auditoría estricta y control de acceso basado en roles (RBAC).
*   **Integración con Python:** Excelente ecosistema (e.g., SQLAlchemy, asyncpg), lo cual encaja perfectamente con un backend en Python (como FastAPI o Django).

### Arquitectura Híbrida Sugerida
*   **Datos Financieros y de Usuarios (Críticos):** **PostgreSQL**. Aquí se guarda el saldo de los usuarios, el historial de transacciones, los retiros y la información KYC personal (encriptada).
*   **Datos de Juego en Tiempo Real (Velocidad):** **Redis** (En Memoria). Para manejar las sesiones en vivo de los usuarios, tablas de clasificación, o mecánicas de *staking* en tiempo real que requieren latencia ultrabaja.

---

## 2. Legislación Vigente: España y Unión Europea (2026)

Este es el punto más sensible. Si el objetivo es que el proyecto **no sea ilegal ni se acerque a lo ilegal**, debes navegar un campo minado legal, especialmente al mezclar juegos de azar/habilidad y criptomonedas.

### A. España: Dirección General de Ordenación del Juego (DGOJ)
*   **Juego de Azar vs. Habilidad:** En España, cualquier juego en el que se arriesgue dinero (o valor equivalente) sobre un resultado futuro e incierto donde intervenga el azar, requiere **Licencia de la DGOJ**. 
*   **El Problema de las Criptomonedas:** Actualmente, la DGOJ **PROHÍBE** a los operadores con licencia española aceptar depósitos o realizar retiros directamente en criptomonedas hacia wallets anónimas o pseudo-anónimas. Los pagos deben ser nominativos (tarjetas, cuentas bancarias a nombre del usuario verificado).
*   **Las posibles "Vías Legales":**
    1.  **Conversión a Fiat obligatoria:** Aceptar pagos en cripto a través de una pasarela de pago legal en España (como Bit2Me o un procesador institucional) que convierta instantáneamente la criptografía a Euros (€) al entrar a la plataforma, y pague en Euros al retirar.
    2.  **Juego puramente de Habilidad (Cero Azar):** Si WinStake.ia es un torneo de esports puro o un juego donde *el 100% del resultado depende de la pericia* (no hay dados, no hay cartas al azar, no hay RNG), puede salir del paraguas de la Ley del Juego, pero los umbrales son muy estrictos y las recompensas cripto siguen sujetas a leyes de prevención de blanqueo de capitales.

### B. Unión Europea: Normativa MiCA (Markets in Crypto-Assets)
*   **Regulación Estricta:** La ley MiCA ya está plenamente vigente en 2026. Si vas a emitir un token propio ("WinStake Token") o retener activos de los usuarios (como un exchange), **necesitas una licencia CASP** (Crypto-Asset Service Provider) válida en la UE.
*   **Prevención de Blanqueo de Capitales (AML/KYC):** No puedes ser una plataforma anónima. Para permitir retiros, estás **obligado por ley europea (DAC8)** a identificar a tus clientes (Know Your Customer: pedir DNI, prueba de residencia) y reportar las transacciones sospechosas.
*   **Retiros y Fiscalidad:** Cada vez que un ciudadano europeo gane criptomonedas y las retire, esa información será cruzada con su hacienda local (ej. la AEAT en España). Debes avisar claramente en tus términos de servicio de las responsabilidades fiscales de los usuarios.

## 3. "Los Peros" en los Retiros

Para que los retiros (exportar criptos) sean completamente legales desde España hacia Europa:
1.  **Verificación Total:** Un usuario **no puede retirar un solo céntimo (o token)** sin haber pasado un KYC estricto para cumplir con las directivas AML de la UE.
2.  **Trazabilidad:** Debes demostrar mediante herramientas forenses de blockchain (ej. Chainalysis) que el dinero que paga o cobra el usuario no proviene de mercados oscuros. Si no lo haces, serás responsable por blanqueo de capitales.
3.  **Límites de Seguridad:** Instaurar períodos de "enfriamiento" o comprobación manual para retiros grandes. Nada de retiros automáticos gigantes sin revisión en los primeros compases del proyecto.

## Resumen del Stack Final para WinStake
*   **Frontend:** Angular + Tauri (Para máxima seguridad cliente y prevención de ingeniería inversa).
*   **Backend:** Python (FastAPI o Django para robustez).
*   **Base de Datos:** PostgreSQL para core financiero + Redis para estados de juego.
*   **Cumplimiento Legal:** KYC obligatorio proveedor (ej. Onfido), Pasarela Crypto Regulada (MiCA compliant), e imposibilidad de operar bajo anonimato si se quiere licencia española.
