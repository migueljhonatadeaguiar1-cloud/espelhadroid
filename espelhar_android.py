"""Espelhamento e controle de Android por ADB sem fio e scrcpy (Windows).

Instalação:
  py -m pip install flask qrcode[pil] pillow
  Instale Android SDK Platform-Tools (adb) e scrcpy e adicione ambos ao PATH.

Uso: conecte PC e celular à mesma rede Wi-Fi; no Android, ative Opções do
desenvolvedor > Depuração sem fio. Use o endereço/porta de pareamento e o
código mostrados em "Parear dispositivo com código". Depois informe a porta
de conexão exibida na tela principal de Depuração sem fio. O código QR abre
uma página de instruções no celular; ele não pareia o dispositivo sozinho.
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from typing import Callable


def dependencias_ausentes() -> list[str]:
    """Verifica pacotes Python e programas externos antes de abrir a janela."""
    faltando = []
    for pacote in ("flask", "qrcode", "PIL"):
        if importlib.util.find_spec(pacote) is None:
            faltando.append(pacote)
    return faltando


missing = dependencias_ausentes()
if missing:
    # Tkinter costuma vir com Python no Windows. A mensagem permite corrigir
    # dependências antes de importar os demais módulos.
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Dependências ausentes",
        "Não encontrei: " + ", ".join(missing) +
        "\n\nInstale as dependências Python com:\n"
        "py -m pip install flask qrcode[pil] pillow\n\n"
        "Instale Android SDK Platform-Tools (adb) e scrcpy, adicione as pastas "
        "ao PATH do Windows e abra este programa novamente.",
    )
    root.destroy()
    raise SystemExit(1)

from flask import Flask
import qrcode
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk


app = Flask(__name__)
app.logger.disabled = True
PAGINA_INSTRUCOES = """<!doctype html><html lang="pt-br"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conectar Android</title>
<body style="font:18px Arial;max-width:720px;margin:40px auto;padding:0 18px">
<h1>Espelhar Android no computador</h1>
<p>O celular e o computador precisam estar conectados à mesma rede Wi-Fi.</p>
<ol><li>No Android, abra Configurações &gt; Sobre o telefone e toque sete vezes em
“Número da versão” (se as Opções do desenvolvedor ainda não estiverem ativas).</li>
<li>Abra Sistema &gt; Opções do desenvolvedor e ative “Depuração sem fio”.</li>
<li>Na opção “Parear dispositivo com código”, informe no computador o IP, a porta
de pareamento e o código exibidos. Autorize a solicitação no celular, se aparecer.</li>
<li>Depois, use o IP e a porta de conexão mostrados na tela principal de
“Depuração sem fio”. A porta de conexão pode ser diferente da porta de pareamento.</li></ol>
<p>O pareamento e a autorização são feitos pelo próprio Android. Esta página não
instala aplicativos nem ignora solicitações do sistema.</p></body></html>"""


@app.get("/")
def instrucoes():
    return PAGINA_INSTRUCOES


def descobrir_ip_local() -> str:
    """Descobre o IP da interface usada para sair à rede, sem enviar dados."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))  # endereço de documentação; sem tráfego útil
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class EspelhadorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Espelhar Android por Wi-Fi")
        self.root.geometry("760x700")
        self.root.minsize(700, 650)
        self.ip_pc = descobrir_ip_local()
        self.adb_exe = shutil.which("adb")
        self.scrcpy_exe = shutil.which("scrcpy")
        self.url = f"http://{self.ip_pc}:5000/"
        self.resultados: queue.Queue[tuple[Callable, tuple]] = queue.Queue()
        self.fechando = False
        self.adb_serial: str | None = None
        self.scrcpy_processo: subprocess.Popen | None = None
        self.config_path = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EspelharAndroid", "device.json")
        self.host_salvo = self.carregar_host_salvo()
        self.server = None
        self.server_thread = threading.Thread(target=self.iniciar_servidor, daemon=True)
        self.server_thread.start()
        self.montar_interface()
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
        self.root.after(100, self.processar_resultados)

    def iniciar_servidor(self):
        try:
            from werkzeug.serving import make_server
            self.server = make_server("0.0.0.0", 5000, app, threaded=True)
            self.server.serve_forever()
        except OSError as exc:
            self.resultados.put((self.mostrar_erro, ("Servidor web", f"Não foi possível abrir a porta 5000: {exc}")))

    def montar_interface(self):
        moldura = ttk.Frame(self.root, padding=14)
        moldura.pack(fill="both", expand=True)
        ttk.Label(moldura, text="Espelhamento Android por Wi-Fi", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(moldura, text=f"Celular e computador devem estar na mesma rede. Página local: {self.url}", wraplength=700).pack(anchor="w", pady=(4, 8))
        try:
            qr = qrcode.make(self.url).convert("RGB").resize((190, 190))
            self.qr_img = ImageTk.PhotoImage(qr)
            ttk.Label(moldura, image=self.qr_img).pack(anchor="w", pady=(0, 8))
        except Exception as exc:
            ttk.Label(moldura, text=f"Não foi possível gerar o QR code: {exc}").pack(anchor="w")
        ttk.Button(moldura, text="Abrir página de instruções no computador", command=lambda: webbrowser.open(self.url)).pack(anchor="w", pady=(0, 10))
        ttk.Label(moldura, text="No Android: ative Opções do desenvolvedor > Depuração sem fio. Em “Parear dispositivo com código”, obtenha IP, porta e código. Após parear, use a porta de conexão indicada na tela principal de Depuração sem fio.", wraplength=710).pack(anchor="w", pady=(0, 10))

        form = ttk.Frame(moldura)
        form.pack(fill="x")
        self.host = tk.StringVar()
        if self.host_salvo:
            self.host.set(self.host_salvo)
        self.pair_port = tk.StringVar()
        self.code = tk.StringVar()
        self.connect_port = tk.StringVar()
        campos = [("IP do celular", self.host), ("Porta de pareamento", self.pair_port), ("Código de pareamento", self.code), ("Porta de conexão", self.connect_port)]
        for linha, (rotulo, var) in enumerate(campos):
            ttk.Label(form, text=rotulo + ":").grid(row=linha, column=0, sticky="w", padx=(0, 8), pady=3)
            ttk.Entry(form, textvariable=var, width=28, show="*" if rotulo.startswith("Código") else "").grid(row=linha, column=1, sticky="w", pady=3)
        self.btn_pair = ttk.Button(form, text="Parear", command=self.parear)
        self.btn_pair.grid(row=0, column=2, padx=10, sticky="w")
        self.btn_connect = ttk.Button(form, text="Conectar e iniciar scrcpy", command=self.conectar, state="disabled")
        self.btn_connect.grid(row=1, column=2, padx=10, sticky="w")
        ttk.Button(form, text="Localizar adb.exe…", command=self.escolher_adb).grid(row=2, column=2, padx=10, sticky="w")
        ttk.Button(form, text="Localizar scrcpy.exe…", command=self.escolher_scrcpy).grid(row=3, column=2, padx=10, sticky="w")
        self.btn_auto = ttk.Button(form, text="Reconectar automaticamente", command=self.reconectar_automaticamente, state="normal" if self.host_salvo else "disabled")
        self.btn_auto.grid(row=4, column=2, padx=10, sticky="w")
        self.status = tk.StringVar(value="Aguardando dados de pareamento do Android.")
        ttk.Label(moldura, textvariable=self.status, wraplength=710).pack(anchor="w", pady=(12, 4))
        ttk.Label(moldura, text="Registro", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.log = tk.Text(moldura, height=7, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=(4, 8))
        ttk.Button(moldura, text="Fechar", command=self.fechar).pack(anchor="e")
        self.registrar("QR code pronto. A página informa como ativar e usar a Depuração sem fio.")
        if self.host_salvo:
            self.registrar(f"Dispositivo lembrado: {self.host_salvo}. Ative a Depuração sem fio no celular e tente reconectar.")
        if not self.adb_exe or not self.scrcpy_exe:
            ausentes = ", ".join(nome for nome, caminho in (("adb.exe", self.adb_exe), ("scrcpy.exe", self.scrcpy_exe)) if not caminho)
            self.registrar(f"Não localizei {ausentes} no PATH. Use os botões 'Localizar' para selecionar os executáveis.")

    def carregar_host_salvo(self) -> str:
        try:
            with open(self.config_path, "r", encoding="utf-8") as arquivo:
                return str(json.load(arquivo).get("host", "")).strip()
        except (OSError, ValueError, AttributeError):
            return ""

    def salvar_host(self, host: str):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as arquivo:
                json.dump({"host": host}, arquivo)
            self.host_salvo = host
            self.btn_auto.configure(state="normal")
        except OSError as exc:
            self.registrar(f"Não consegui salvar o IP para reconexões futuras: {exc}")

    def reconectar_automaticamente(self):
        if not self.adb_exe or not self.scrcpy_exe:
            messagebox.showwarning("Programas não localizados", "Localize adb.exe e scrcpy.exe antes de conectar.", parent=self.root)
            return
        host = self.host.get().strip() or self.host_salvo
        if not host:
            messagebox.showwarning("IP necessário", "Faça o pareamento inicial ou informe o IP do celular.", parent=self.root)
            return
        self.status.set("Procurando o celular na rede… Confirme que Depuração sem fio está ativada.")
        self.btn_auto.configure(state="disabled")
        threading.Thread(target=self.worker_reconectar, args=(host,), daemon=True).start()

    def worker_reconectar(self, host: str):
        try:
            proc = subprocess.run([self.adb_exe, "mdns", "services"], text=True, capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            linhas = [linha for linha in proc.stdout.splitlines() if "_adb-tls-connect._tcp" in linha]
            endpoints = []
            for linha in linhas:
                encontrados = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}", linha)
                endpoints.extend(ep for ep in encontrados if ep.split(":")[0] == host)
            if not endpoints and len(linhas) == 1:
                endpoints = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}", linhas[0])
            if not endpoints:
                self.resultados.put((self.reconexao_falhou, ("Não encontrei serviço ADB sem fio para esse IP. Verifique se o celular está na mesma Wi-Fi e com Depuração sem fio ativada. Talvez seja necessário fazer o pareamento inicial novamente.",)))
                return
            destino = endpoints[0]
            ligado = subprocess.run([self.adb_exe, "connect", destino], text=True, capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            devices = subprocess.run([self.adb_exe, "devices"], text=True, capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            conectado = any(line.split()[:2] == [destino, "device"] for line in devices.stdout.splitlines())
            self.resultados.put((self.conexao_concluida, (conectado, (ligado.stdout + "\n" + ligado.stderr + "\n" + devices.stdout).strip(), destino if conectado else None)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.resultados.put((self.reconexao_falhou, (str(exc),)))

    def reconexao_falhou(self, msg: str):
        self.btn_auto.configure(state="normal")
        self.status.set("Reconexão automática não encontrou o celular.")
        self.registrar(msg)
        messagebox.showwarning("Reconexão não concluída", msg, parent=self.root)

    def escolher_adb(self):
        caminho = filedialog.askopenfilename(title="Selecione adb.exe", filetypes=[("Executável do Windows", "adb.exe"), ("Todos os arquivos", "*.*")], parent=self.root)
        if caminho:
            self.adb_exe = caminho
            self.registrar(f"ADB selecionado: {caminho}")

    def escolher_scrcpy(self):
        caminho = filedialog.askopenfilename(title="Selecione scrcpy.exe", filetypes=[("Executável do Windows", "scrcpy.exe"), ("Todos os arquivos", "*.*")], parent=self.root)
        if caminho:
            self.scrcpy_exe = caminho
            self.registrar(f"scrcpy selecionado: {caminho}")

    def registrar(self, texto: str):
        if self.fechando:
            return
        self.log.configure(state="normal")
        self.log.insert("end", texto.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def mostrar_erro(self, titulo: str, texto: str):
        self.status.set(texto)
        self.registrar(texto)
        messagebox.showerror(titulo, texto, parent=self.root)

    def processar_resultados(self):
        if self.fechando:
            return
        try:
            while True:
                funcao, args = self.resultados.get_nowait()
                funcao(*args)
        except queue.Empty:
            pass
        self.root.after(100, self.processar_resultados)

    @staticmethod
    def validar_porta(valor: str) -> bool:
        try:
            return 1 <= int(valor) <= 65535
        except ValueError:
            return False

    def parear(self):
        if not self.adb_exe:
            messagebox.showwarning("ADB não localizado", "Use 'Localizar adb.exe' para selecionar o adb.exe instalado.", parent=self.root)
            return
        host, port, code = self.host.get().strip(), self.pair_port.get().strip(), self.code.get().strip()
        if not host or not self.validar_porta(port) or not code:
            messagebox.showwarning("Dados incompletos", "Informe o IP, a porta de pareamento e o código exibidos pelo Android.", parent=self.root)
            return
        self.btn_pair.configure(state="disabled")
        self.status.set("Pareando com o Android…")
        threading.Thread(target=self.worker_parear, args=(host, port, code), daemon=True).start()

    def worker_parear(self, host: str, port: str, code: str):
        try:
            # O adb aceita o código como argumento, evitando depender de prompt interativo.
            proc = subprocess.run([self.adb_exe, "pair", f"{host}:{port}", code], text=True, capture_output=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            saida = (proc.stdout + "\n" + proc.stderr).strip()
            ok = proc.returncode == 0 and "successfully paired" in saida.lower()
            self.resultados.put((self.pareamento_concluido, (ok, saida or f"adb pair terminou com código {proc.returncode}")))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.resultados.put((self.pareamento_concluido, (False, str(exc))))

    def pareamento_concluido(self, ok: bool, saida: str):
        self.btn_pair.configure(state="normal")
        self.registrar(saida)
        if ok:
            self.salvar_host(self.host.get().strip())
            self.status.set("Pareamento concluído. Informe a porta de conexão mostrada na tela principal da Depuração sem fio.")
            self.btn_connect.configure(state="normal")
            self.code.set("")
        else:
            self.status.set("Falha no pareamento. Confira IP, porta, código e a rede Wi-Fi.")
            messagebox.showerror("Falha no pareamento", saida + "\n\nO código pode expirar; gere outro no Android e tente novamente.", parent=self.root)

    def conectar(self):
        if not self.adb_exe or not self.scrcpy_exe:
            messagebox.showwarning("Programa não localizado", "Use os botões 'Localizar adb.exe' e 'Localizar scrcpy.exe' para selecionar os executáveis.", parent=self.root)
            return
        host, port = self.host.get().strip(), self.connect_port.get().strip()
        if not host or not self.validar_porta(port):
            messagebox.showwarning("Porta inválida", "Informe a porta de conexão exibida na tela principal de Depuração sem fio.", parent=self.root)
            return
        self.btn_connect.configure(state="disabled")
        self.status.set("Conectando e verificando autorização ADB…")
        threading.Thread(target=self.worker_conectar, args=(host, port), daemon=True).start()

    def worker_conectar(self, host: str, port: str):
        try:
            destino = f"{host}:{port}"
            proc = subprocess.run([self.adb_exe, "connect", destino], text=True, capture_output=True, timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            saida = (proc.stdout + "\n" + proc.stderr).strip()
            if proc.returncode != 0 or "unable to connect" in saida.lower() or "failed" in saida.lower():
                self.resultados.put((self.conexao_concluida, (False, saida or "adb connect falhou", None)))
                return
            devices = subprocess.run([self.adb_exe, "devices"], text=True, capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            conectado = any(line.split()[:2] == [destino, "device"] for line in devices.stdout.splitlines())
            self.resultados.put((self.conexao_concluida, (conectado, saida + "\n\n" + devices.stdout.strip(), destino if conectado else None)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.resultados.put((self.conexao_concluida, (False, str(exc), None)))

    def conexao_concluida(self, ok: bool, saida: str, serial: str | None):
        self.btn_connect.configure(state="normal")
        self.btn_auto.configure(state="normal" if self.host_salvo else "disabled")
        self.registrar(saida)
        if not ok:
            self.status.set("ADB não confirmou a conexão. Confira IP/porta e aceite a autorização no celular.")
            messagebox.showwarning("Dispositivo não autorizado", saida + "\n\nConfira a porta de conexão e aceite no Android a solicitação de depuração, se aparecer.", parent=self.root)
            return
        self.adb_serial = serial
        self.salvar_host(serial.split(":")[0])
        self.status.set("ADB conectado. Iniciando scrcpy; a tela do celular abrirá em outra janela.")
        threading.Thread(target=self.iniciar_scrcpy, args=(serial,), daemon=True).start()

    def iniciar_scrcpy(self, serial: str):
        try:
            proc = subprocess.Popen([self.scrcpy_exe, "-s", serial, "--always-on-top"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.scrcpy_processo = proc
            self.resultados.put((self.scrcpy_iniciado, ()))
            _, erro = proc.communicate()
            self.scrcpy_processo = None
            if not self.fechando and proc.returncode:
                msg = (erro or "").strip() or f"scrcpy terminou com código {proc.returncode}"
                self.resultados.put((self.scrcpy_terminado, (msg,)))
        except OSError as exc:
            self.resultados.put((self.mostrar_erro, ("Erro ao iniciar scrcpy", str(exc))))

    def scrcpy_iniciado(self):
        self.status.set("Espelhamento ativo. Você pode interagir com o celular pela janela do scrcpy.")
        self.registrar("scrcpy iniciado.")

    def scrcpy_terminado(self, msg: str):
        self.status.set("A janela do scrcpy foi encerrada.")
        self.registrar(msg)

    def fechar(self):
        self.fechando = True
        if self.scrcpy_processo and self.scrcpy_processo.poll() is None:
            self.scrcpy_processo.terminate()
        try:
            if self.server:
                self.server.shutdown()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    EspelhadorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
