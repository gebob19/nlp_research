import torch
import torch.nn as nn
import torch.nn.functional as F
# from .layer_norm import LayerNorm


class SublayerConnection(nn.Module):
    """
    A residual connection followed by a layer norm.
    Note for code simplicity the norm is first as opposed to last.
    """

    def __init__(self, device, size, dropout, attention_dropout):
        super().__init__()
        self.norm = nn.LayerNorm(size, eps=1e-12)
        self.dropout = nn.Dropout(dropout)
        self.attention_dropout = attention_dropout
        if attention_dropout:
            self.layer_embedding = torch.randn((size), device=device, requires_grad=True)
            self.task_attention = TaskAttention(device, dropout)

    def forward(self, x, sublayer, lengths):
        "Apply residual connection to any sublayer with the same size."
        h = sublayer(x)
        # apply dropout of choice
        if self.attention_dropout and self.training:
            bs = x.size(1)
            batch_task = self.layer_embedding.repeat(bs).view(bs, -1).unsqueeze(-1)
            h = h * self.task_attention(h, batch_task, lengths)
        else:
            h = self.dropout(h)
        return self.norm(x + h)

    def update_dropout(self, new_dropout):
        if self.attention_dropout:
            self.task_attention.dropout = new_dropout

class TaskAttention(nn.Module):
    def __init__(self, device, dropout):
        super().__init__()
        self.device = device
        self.dropout = dropout
        
    def forward(self, q, k, lengths):
        q = q.transpose(0, 1) 
        
        # restricted attention dropout
        w = torch.bmm(q, k).squeeze(-1)

        # n is the # words to ignore 
        n = int(w.size(-1) * self.dropout)
        n = n if n != 0 else 1

        # inverse probability hack for multinomial sampling
        mx, _ = torch.max(w, -1)
        mx = mx.unsqueeze(-1)
        p_inv = F.softmax(mx - w, -1)
        attnmask = torch.multinomial(p_inv, n)
        
        # create restricted attention mask
        byte_mask = torch.ones_like(w)
        for bm, mask in zip(torch.split(byte_mask, 1), attnmask):
            bm.squeeze()[mask] = 0. 
        # # ignore paddings
        # for i, length in enumerate(lengths):
        #     bm[i, length:, :] = 0.

        w = byte_mask.to(self.device).unsqueeze(-1)

        w = w.transpose(0, 1)
        return w