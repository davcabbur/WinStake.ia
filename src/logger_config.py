"""
WinStake.ia — Configuración Centralizada de Logging
Configura la rotación de logs (RotatingFileHandler) para evitar que los logs crezcan indefinidamente.
"""

import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(logger_name: str = "WinStake") -> logging.Logger:
    """
    Configura y devuelve un logger con salida dual (Consola + Fichero rotatorio).
    """
    logger = logging.getLogger(logger_name)
    
    # Si ya tiene handlers, no duplicar
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 2. File Handler (con rotación)
    log_dir = "data"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")
    
    try:
        # Max 5 MB por archivo, conservar los últimos 3 backups
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except PermissionError:
        print("⚠️ Advertencia: Sin permisos para escribir el archivo de log rotatorio.")

    # Asegurar que el logger raíz también coja esta configuración básica 
    # por si otros módulos hacen logging.info() directo
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    return logger
