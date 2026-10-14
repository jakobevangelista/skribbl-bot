# Skribbl guesser

A Chrome extension reads the live hint and the drawing canvas on skribbl.io. A local vision model names what the drawing might be. The page shows those words. Clicking one fills the chat box. Nothing is submitted for you.

## Run the guess server

The machine this was written for has an RTX 3070 Ti (8 GB). Qwen3.5-4B at the default Ollama quant fits that card.

```sh
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#python3 nixpkgs#ollama-cuda
ollama serve
```

`ollama-cuda` needs the CUDA license override above. Without it, Nix refuses to evaluate the package.

In another shell:

```sh
ollama pull qwen3.5:4b
nix shell nixpkgs#python3
python server/guess.py
```

The server listens on `http://127.0.0.1:8765`. `GET /health` reports the model name. Optional word list: `words/en.txt`, one answer per line. Words in that file are only added when two or fewer letters are still hidden. A model guess is kept even when it is absent from the list.

`MODEL_URL` defaults to Ollama's `http://127.0.0.1:11434/api/chat`. Point it at an OpenAI-compatible `/v1/chat/completions` endpoint (llama.cpp `llama-server`) if Ollama will not accept the image. `MODEL_NAME` defaults to `qwen3.5:4b`.

One-shot from a PNG:

```sh
python server/guess.py --image drawing.png --hints _ _ a _ _ --word-length 6
```

## Load the extension

1. Open `chrome://extensions`.
2. Turn on Developer mode.
3. Load unpacked and choose the `extension` directory.
4. Join a game as a guesser. The panel sits at the top left.

The panel stays quiet while you are drawing, on the home screen, or while the round overlay is up (choosing a word, the reveal, or the scoreboard). A newly revealed letter refilters the last model reply and does not run vision again. The × on a suggestion hides it until the next word.

## What it reads

From the current skribbl.io document and `js/game.js`:

| Thing | Selector |
| --- | --- |
| Hint characters | `#game-word .hints .container > .hint` |
| Length label, such as `3 5` | `#game-word .hints .container > .word-length` |
| The word, when you are drawing | `#game-word .word` |
| Drawing | `#game-canvas canvas` (one canvas, 800×600) |
| Between-round overlay | `#game-canvas .overlay.show` |
| Chat box | `#game-chat input` |

## Tests

```sh
nix shell nixpkgs#python3
python -m unittest discover -s server -v
```
