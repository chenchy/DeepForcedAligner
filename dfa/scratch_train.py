import argparse
import numpy as np
import torch
from torch import optim
from torch.nn import CTCLoss

from dfa.dataset import new_dataloader
from dfa.model import Aligner
from dfa.paths import Paths
from dfa.text import Tokenizer
from dfa.utils import read_config, unpickle_binary


def to_device(batch: dict, device: torch.device) -> tuple:
    tokens, mel, tokens_len, mel_len = batch['tokens'], batch['mel'], \
                                       batch['tokens_len'], batch['mel_len']
    tokens, mel, tokens_len, mel_len = tokens.to(device), mel.to(device), \
                                       tokens_len.to(device), mel_len.to(device)
    return tokens, mel, tokens_len, mel_len


def char_error(pred: torch.tensor, target: torch.tensor) -> float:
    bs = pred.size(0)
    sum_diff = 0
    pred = pred.detach().cpu().numpy()
    target = pred.detach().cpu().numpy()
    for i in bs:
        sum_diff += len(np.setdiff1d(pred[i], target[i]))
    return sum_diff / bs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Preprocessing for DeepForcedAligner.')
    parser.add_argument('--config', '-c', default='config.yaml', help='Points to the config file.')
    parser.add_argument('--model', '-m', help='Points to the a model file to restore.')

    args = parser.parse_args()

    config = read_config(args.config)
    paths = Paths(**config['paths'])
    symbols = unpickle_binary(paths.data_dir / 'symbols.pkl')
    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

    model = Aligner(n_mels=config['audio']['n_mels'],
                    num_symbols=len(symbols)+1,
                    **config['model']).to(device)
    optim = optim.Adam(model.parameters(), lr=1e-4)
    paths = Paths(**config['paths'])
    ctc_loss = CTCLoss()
    tokenizer = Tokenizer(symbols)
    dataloader = new_dataloader(dataset_path=paths.data_dir / 'dataset.pkl', mel_dir=paths.mel_dir,
                                token_dir=paths.token_dir, batch_size=16)



    for epoch in range(1, 1000):
        char_error_sum = 0
        for i, batch in enumerate(dataloader):
            tokens, mel, tokens_len, mel_len = to_device(batch, device)
            pred = model(mel)
            pred = pred.transpose(0, 1).log_softmax(2)
            loss_ctc = ctc_loss(pred, tokens, mel_len, tokens_len)
            loss_blank = torch.softmax(pred, dim=-1)[:, :, 0]
            loss = loss_ctc + loss_blank
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            if i % 100 == 0:
                print(f'{i} / {len(dataloader)} loss ctc: {loss_ctc.item()} loss blank: {loss_blank.item()}')
                first_tar = tokens[0].detach().cpu().numpy().tolist()
                first_pred = pred.transpose(0, 1)[0].max(1)[1].detach().cpu().numpy().tolist()
                text = tokenizer.decode(first_pred)
                tar_text = tokenizer.decode(first_tar)

                print(text[:100])
                print(tar_text[:100])

        latest_checkpoint = paths.checkpoint_dir / 'latest_model.pt'
        print(f'Saving checkpoint to {latest_checkpoint}')
        torch.save({
            'model': model.state_dict(),
            'optim': optim.state_dict(),
            'config': config,
            'symbols': symbols,
        }, latest_checkpoint)