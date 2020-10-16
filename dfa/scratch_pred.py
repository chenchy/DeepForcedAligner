from pathlib import Path

import torch
import numpy as np
from dfa.audio import Audio
from dfa.extract_durations import extract_durations_with_dijkstra
from dfa.model import Aligner
from dfa.text import Tokenizer
from dfa.utils import read_metafile

if __name__ == '__main__':

    checkpoint = torch.load('/Users/cschaefe/dfa_checkpoints/latest_model.pt', map_location=torch.device('cpu'))
    config = checkpoint['config']
    symbols = checkpoint['symbols']
    audio = Audio(**config['audio'])
    tokenizer = Tokenizer(symbols)
    model = Aligner.from_checkpoint(checkpoint).eval()
    print(f'model step {model.get_step()}')

    main_dir = Path('/Users/cschaefe/datasets/MFA_LJ')
    text_dict = read_metafile(main_dir)
    file_id = 'LJ050-0278'
    wav = audio.load_wav(main_dir / f'wavs/{file_id}.wav')
    text = text_dict[file_id]

    target = np.array(tokenizer(text))

    mel = audio.wav_to_mel(wav)
    mel = torch.tensor(mel).float().unsqueeze(0)

    pred = model(mel)

    pred_max = pred[0].max(1)[1].detach().cpu().numpy().tolist()
    pred_text = tokenizer.decode(pred_max)

    pred = torch.softmax(pred, dim=-1)
    pred = pred.detach()[0].numpy()

    target_len = target.shape[0]
    pred_len = pred.shape[0]

    pred_max = np.zeros((pred_len, target_len))

    for i in range(pred.shape[0]):
        pred_max[i] = pred[i, target]

    durations = extract_durations_with_dijkstra(target, pred_max, tokenizer)
    expanded_string = ''.join([text[i] * dur for i, dur in enumerate(list(durations))])
    print(text)
    print(pred_text)
    print(expanded_string)
    print(durations)



