import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

from model.components.decoder import Decoder
from model.utils.mask import generate_mask
from typing import Union, Callable

import os

device = torch.device('cuda' if torch.cuda.is_available() else "cpu")

class GPTModel(nn.Module):
    def __init__(self, vocab_size: int, n: int, embedding_dim: int, heads: int, d_ff: int, dropout_rate: float, eps: float,activation: Union[str, Callable[[torch.Tensor], torch.Tensor]]):
        super().__init__()
        self.embedding_layer = nn.Embedding(num_embeddings=vocab_size, embedding_dim=embedding_dim)
        self.decoder = Decoder(vocab_size=vocab_size, n=n, embedding_dim=embedding_dim, heads=heads, d_ff=d_ff, dropout_rate=dropout_rate, eps=eps, activation=activation)

    def forward(self, x: torch.Tensor, mask: torch.Tensor, training: bool):
        x = self.embedding_layer(x)
        x = self.decoder(x, mask, training)

        return x


class GPT:
    def __init__(self,
                vocab_size: int, 
                n: int = 12, 
                embedding_dim: int = 768, 
                heads: int = 12, 
                d_ff: int = 2048, 
                dropout_rate: float = 0.1, 
                eps: float = 0.1,
                activation: Union[str, Callable[[torch.Tensor], torch.Tensor]] = F.relu,
                checkpoint: str = None):
        self.model = GPTModel(vocab_size=vocab_size, n=n, embedding_dim=embedding_dim, heads=heads, d_ff=d_ff, dropout_rate=dropout_rate, eps=eps, activation=activation)
        self.embedding_dim = embedding_dim
        self.checkpoint = checkpoint
    
    def build_dataset(self, inputs: torch.Tensor, batch_size: int):
        dataset = TensorDataset((inputs))
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
        return dataloader

    def loss_function(self, outputs: torch.Tensor, labels: torch.Tensor):
        length = labels.size(1) 
        criterion = nn.CrossEntropyLoss()
        total_loss = 0.0
        for item in range(length):
            loss = criterion(outputs[:, item, :], labels[:, item])
            total_loss += loss
        total_loss = total_loss/length
        return total_loss

    def save_model(self, path: str):
        torch.save({
            'model_state_dict': self.model.state_dict()
        }, path)
        print(f"Your Model Saved at {path}")

    def load_model(self, path: str):
        if os.path.exists(path) == True:
            checkpoint = torch.load(path)
            self.model.load_state_dict(checkpoint['model_state_dict'])

    def info(self):
        self.load_model(self.checkpoint)
        print("Model's State Dict: ")
        for param_tensor in self.model.state_dict():
            print(param_tensor, "\t", self.model.state_dict()[param_tensor].size())
        print("===========================================================================================")
    
    def fit(self, sequences: torch.Tensor, batch_size: int = 1, epochs: int = 1, learning_rate: float = 0.0006):
        if self.checkpoint is not None:
            self.load_model(self.checkpoint)

        optimizer = optim.Adam(params=self.model.parameters(), lr=learning_rate)
        dataloader = self.build_dataset(sequences, batch_size)

        self.model.to(device)

        for epoch in range(epochs):
            running_loss = 0.0

            for index, data in enumerate(dataloader, 0):
                data = data[0]

                _, look_ahead_mask = generate_mask(data)

                data = data.to(device)
                look_ahead_mask = look_ahead_mask.to(device)

                optimizer.zero_grad()

                outputs = self.model(data, look_ahead_mask, True)

                loss = self.loss_function(outputs, data)

                loss.backward()
                optimizer.step()

                running_loss += loss.item()
                
                if index%batch_size == 0:
                    print(f"Epoch: {epoch + 1} Batch: {index+1} Loss: {(running_loss/batch_size):.2f}")
                    running_loss = 0.0

    def predict(self, inputs: torch.Tensor, max_length: int, end_token: int):
        self.load_model(self.checkpoint)
        for i in range(max_length - inputs.size(1)):
            _, look_ahead_mask = generate_mask(inputs)

            preds = self.model(inputs, look_ahead_mask, False)

            preds = preds[:, -1, :]

            predicted_id = torch.max(preds, dim=-1)

            if predicted_id == end_token:
                break

            inputs = torch.concat([inputs, predicted_id], dim=-1)

        return inputs
    