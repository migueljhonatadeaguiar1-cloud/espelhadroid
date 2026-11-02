# espelhadroid
Aplicativo em Python para parear um Android pela Depuração sem fio e abrir o `scrcpy` para espelhar e controlar o celular pelo computador.

Requisitos

- Windows 10 ou 11
- Android 11 ou superior com **Opções do desenvolvedor > Depuração por Wi-Fi**
- Python 3.10 ou superior com Tkinter
- Android SDK Platform-Tools (`adb`)
- `scrcpy` para Windows

## Instalação

1. Instale as dependências Python:

   ```powershell
   py -m pip install -r requirements.txt
   ```

2. Baixe o [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) e extraia o ZIP. O executável `adb.exe` fica dentro de `platform-tools`.
3. Baixe o [scrcpy oficial para Windows](https://github.com/Genymobile/scrcpy/releases/latest) e extraia o pacote.
4. Execute `espelhar_android.py`:

   ```powershell
   py espelhar_android.py
   ```

   Se `adb.exe` ou `scrcpy.exe` não estiverem no `PATH`, use os botões **Localizar** na janela para selecionar cada arquivo.

## Primeiro pareamento

1. Conecte o celular e o computador à mesma rede Wi-Fi.
2. No Android, ative **Depuração por Wi-Fi** nas Opções do desenvolvedor.
3. Toque em **Parear o dispositivo com um código de pareamento** no celular.
4. No programa, informe o IP, a porta e o código temporário mostrados nessa tela e clique em **Parear**.
5. Volte à tela principal de Depuração por Wi-Fi e clique em **Reconectar automaticamente** no computador. Se a busca automática não encontrar o aparelho, informe a porta de conexão da tela principal e clique em **Conectar e iniciar scrcpy**.
6. Aceite no celular qualquer solicitação de autorização de depuração.

> O QR code do programa abre uma página local com instruções. Ele não substitui o pareamento nem as autorizações do Android. O aplicativo guarda o último IP localmente para facilitar futuras reconexões.

## Arquivos

- `espelhar_android.py` — aplicativo Python.
- `requirements.txt` — dependências Python.

Os executáveis `adb.exe` e `scrcpy.exe` não estão incluídos; baixe-os das fontes oficiais indicadas acima.
