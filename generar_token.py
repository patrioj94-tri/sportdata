"""Genera tu token de Garmin para usar Patri's Data Lab sin contraseña.

Por qué hace falta: Garmin bloquea el login con contraseña cuando viene de un servidor
(la app publicada). Este programa hace ese login UNA vez desde tu ordenador, donde sí
funciona, y guarda el token resultante. El token vale ~1 año y NO contiene tu contraseña.

Cómo usarlo (solo hace falta Python instalado):
    1. Abre una terminal en esta carpeta
    2. Ejecuta:  python generar_token.py
    3. Escribe tu email y contraseña de Garmin (la contraseña no se guarda)
    4. Se abre un archivo con tu token: cópialo entero y pégalo en la app

Guarda ese token como si fuera tu contraseña: da acceso a tu cuenta de Garmin.
"""
import getpass
import os
import subprocess
import sys
import tempfile

try:
    from garminconnect import Garmin
except ImportError:
    print("Falta la librería garminconnect. Instálala con:  pip install garminconnect")
    sys.exit(1)


def main():
    print("=" * 60)
    print("  Generador de token para Patri's Data Lab")
    print("=" * 60)
    print("Tu contraseña se usa solo para este login y no se guarda.\n")

    email = input("Email de Garmin: ").strip()
    password = getpass.getpass("Contraseña de Garmin (no se verá al escribir): ")

    if not email or not password:
        print("\nHace falta email y contraseña.")
        sys.exit(1)

    print("\nConectando con Garmin...")
    token_dir = tempfile.mkdtemp(prefix="garmin_token_")
    try:
        client = Garmin(email, password)
        client.login()
        client.garth.dump(token_dir)
    except Exception as e:
        print(f"\nNo se pudo iniciar sesión: {e}")
        print("Comprueba el email y la contraseña. Si Garmin te pide verificación en dos pasos,")
        print("desactívala temporalmente o usa el código que te envíe.")
        sys.exit(1)

    token_file = os.path.join(token_dir, "garmin_tokens.json")
    if not os.path.exists(token_file):
        print("\nEl login funcionó pero no se generó el archivo de token. Inténtalo de nuevo.")
        sys.exit(1)

    # Se guarda junto al programa para que sea fácil de encontrar
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MI_TOKEN_GARMIN.txt")
    with open(token_file, "r", encoding="utf-8") as src, open(out_path, "w", encoding="utf-8") as dst:
        dst.write(src.read().strip())

    print("\n¡Listo! Tu token está en:")
    print(f"   {out_path}")
    print("\nAbre ese archivo, copia TODO su contenido y pégalo en la app,")
    print("en la barra lateral, en la opción '🔑 Token'.")
    print("\nCuando lo hayas pegado, puedes borrar el archivo.")

    if sys.platform == "win32":
        subprocess.Popen(["notepad", out_path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-t", out_path])


if __name__ == "__main__":
    main()
