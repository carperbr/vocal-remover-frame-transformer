import torch
from torch import nn
import torch.nn.functional as F
import math
from lib import spec_utils

class FrameTransformer(nn.Module):
    def __init__(self, channels, n_fft=2048, feedforward_dim=512, num_bands=4, num_encoders=1, num_decoders=1, cropsize=256, bias=False):
        super(FrameTransformer, self).__init__()
        self.max_bin = n_fft // 2
        self.output_bin = n_fft // 2 + 1

        self.enc1 = FrameConv(2, channels, kernel_size=3, padding=1, stride=1)
        self.enc2 = FrameEncoder(channels * 1, channels * 2, kernel_size=3, stride=2, padding=1)
        self.enc3 = FrameEncoder(channels * 2, channels * 4, kernel_size=3, stride=2, padding=1)
        self.enc4 = FrameEncoder(channels * 4, channels * 6, kernel_size=3, stride=2, padding=1)
        self.enc5 = FrameEncoder(channels * 6, channels * 8, kernel_size=3, stride=2, padding=1)
        
        self.dec4_transformer = nn.ModuleList([FramePrimerDecoder(channels * 8 + i, channels * 8, num_bands, cropsize, n_fft, downsamples=4, feedforward_dim=feedforward_dim, bias=bias) for i in range(num_decoders)])
        self.dec4 = FrameDecoder(channels * (6 + 8) + num_decoders, channels * 6, kernel_size=3, padding=1)

        self.dec3_transformer = nn.ModuleList([FramePrimerDecoder(channels * 6 + i, channels * 6, num_bands, cropsize, n_fft, downsamples=3, feedforward_dim=feedforward_dim, bias=bias) for i in range(num_decoders)])
        self.dec3 = FrameDecoder(channels * (4 + 6) + num_decoders, channels * 4, kernel_size=3, padding=1)

        self.dec2_transformer = nn.ModuleList([FramePrimerDecoder(channels * 4 + i, channels * 4, num_bands, cropsize, n_fft, downsamples=2, feedforward_dim=feedforward_dim, bias=bias) for i in range(num_decoders)])
        self.dec2 = FrameDecoder(channels * (2 + 4) + num_decoders, channels * 2, kernel_size=3, padding=1)

        self.dec1_transformer = nn.ModuleList([FramePrimerDecoder(channels * 2 + i, channels * 2, num_bands, cropsize, n_fft, downsamples=1, feedforward_dim=feedforward_dim, bias=bias) for i in range(num_decoders)])
        self.dec1 = FrameDecoder(channels * (1 + 2) + num_decoders, channels * 1, kernel_size=3, padding=1)

        self.out_transformer = nn.ModuleList([FramePrimerDecoder(channels + i, channels, num_bands, cropsize, n_fft, downsamples=0, feedforward_dim=feedforward_dim, bias=bias) for i in range(num_decoders)])
        self.out = FrameDecoder(channels + num_decoders, 2, kernel_size=3, padding=1)

    def __call__(self, x):
        x = x[:, :, :self.max_bin]

        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        e5 = self.enc5(e4)

        h = e5
        for module in self.dec4_transformer:
            t = module(h, skip=e5)
            h = torch.cat((h, t), dim=1)
            
        h = self.dec4(h, e4)        
        for module in self.dec3_transformer:
            t = module(h, skip=e4)
            h = torch.cat((h, t), dim=1)

        h = self.dec3(h, e3)        
        for module in self.dec2_transformer:
            t = module(h, skip=e3)
            h = torch.cat((h, t), dim=1)

        h = self.dec2(h, e2)        
        for module in self.dec1_transformer:
            t = module(h, skip=e2)
            h = torch.cat((h, t), dim=1)

        h = self.dec1(h, e1)
        for module in self.out_transformer:
            t = module(h, skip=e1)
            h = torch.cat((h, t), dim=1)

        out = self.out(h)

        return F.pad(
            input=torch.sigmoid(out),
            pad=(0, 0, 0, self.output_bin - out.size()[2]),
            mode='replicate'
        )
        
class FrameEncoder(nn.Module):
    def __init__(self, nin, nout, kernel_size=3, stride=1, padding=1, activ=nn.LeakyReLU):
        super(FrameEncoder, self).__init__()
        self.conv1 = FrameConv(nin, nout, kernel_size, 1, padding, activate=activ)
        self.conv2 = FrameConv(nout, nout, kernel_size, stride, padding, activate=activ)

    def __call__(self, x):
        h = self.conv1(x)
        h = self.conv2(h)

        return h

class FrameDecoder(nn.Module):
    def __init__(self, nin, nout, kernel_size=3, padding=1, activ=nn.LeakyReLU, dropout=False):
        super(FrameDecoder, self).__init__()
        self.conv = FrameConv(nin, nout, kernel_size, 1, padding, activate=activ)
        self.dropout = nn.Dropout2d(0.1) if dropout else None

    def __call__(self, x, skip=None):
        if skip is not None:
            x = F.interpolate(x, size=(skip.shape[2],skip.shape[3]), mode='bilinear', align_corners=True)
            skip = spec_utils.crop_center(skip, x)
            x = torch.cat([x, skip], dim=1)

        h = self.conv(x)

        if self.dropout is not None:
            h = self.dropout(h)

        return h

class FramePrimerDecoder(nn.Module):
    def __init__(self, channels, mem_channels, num_bands=4, cropsize=256, n_fft=2048, feedforward_dim=2048, downsamples=0, bias=False, dropout=0.1):
        super(FramePrimerDecoder, self).__init__()

        bins = (n_fft // 2)
        if downsamples > 0:
            for _ in range(downsamples):
                bins = ((bins - 1) // 2) + 1

        self.bins = bins
        self.cropsize = cropsize
        self.num_bands = num_bands

        self.relu = nn.ReLU(inplace=True)        
        self.in_project = nn.Linear(channels, 1, bias=bias)
        self.skip_project = nn.Linear(mem_channels, 1, bias=bias)

        self.self_attention = MultibandFrameAttention(num_bands, bins, cropsize)
        self.norm1 = nn.LayerNorm(bins)

        self.skip_attention = MultibandFrameAttention(num_bands, bins, cropsize)
        self.norm2 = nn.LayerNorm(bins)

        self.linear1 = nn.Linear(bins, feedforward_dim)
        self.linear2 = nn.Linear(feedforward_dim, bins)
        self.norm3 = nn.LayerNorm(bins)

    def __call__(self, x, skip):
        x = self.in_project(x.transpose(1,3)).squeeze(3)
        skip = self.skip_project(skip.transpose(1,3)).squeeze(3)

        h = self.norm1(x)
        h = self.self_attention(h)
        x = x + h

        h = self.norm2(x)
        h = self.skip_attention(h, mem=skip)
        x = x + h

        h = self.linear2(torch.square(self.relu(self.linear1(x))))
        x = self.norm3(x + h)
                
        return x.transpose(1, 2).unsqueeze(1)

class FrameTransformerBlock(nn.Module):
    def __init__(self, channels, mem_channels, num_bands=4, cropsize=256, n_fft=2048, feedforward_dim=2048, downsamples=0, bias=False, dropout=0.1):
        super(FrameTransformerBlock, self).__init__()

        bins = (n_fft // 2)
        if downsamples > 0:
            for _ in range(downsamples):
                bins = ((bins - 1) // 2) + 1

        self.bins = bins
        self.cropsize = cropsize
        self.num_bands = num_bands

        self.relu = nn.ReLU(inplace=True)
        
        self.in_project = nn.Linear(channels, 1, bias=bias)
        self.in_norm = nn.LayerNorm(bins)

        self.mem_project = nn.Linear(mem_channels, 1, bias=bias)
        self.mem_norm = nn.LayerNorm(bins)

        self.self_attn1 = MultibandFrameAttention(num_bands, bins, cropsize)
        self.enc_attn1 = MultibandFrameAttention(num_bands, bins, cropsize)
        self.norm1 = nn.LayerNorm(bins)
        self.dropout1 = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        self.conv1L = nn.Sequential(
            nn.Conv1d(bins, bins, kernel_size=11, padding=5, groups=bins, bias=bias),
            nn.Conv1d(bins, feedforward_dim * 2, kernel_size=1, padding=0, bias=bias))
        self.conv1R = nn.Sequential(
            nn.Conv1d(bins, bins, kernel_size=7, padding=3, groups=bins, bias=bias),
            nn.Conv1d(bins, feedforward_dim // 2, kernel_size=1, padding=0, bias=bias))
        self.norm2 = nn.LayerNorm(feedforward_dim * 2)
        self.conv2 = nn.Sequential(
            nn.Conv1d(feedforward_dim * 2, feedforward_dim * 2, kernel_size=7, padding=3, groups=feedforward_dim*2, bias=bias),
            nn.Conv1d(feedforward_dim * 2, bins, kernel_size=1, padding=0, bias=bias))
        self.norm3 = nn.LayerNorm(bins)
        self.dropout2 = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        self.self_attn2 = MultibandFrameAttention(num_bands, bins, cropsize)
        self.norm4 = nn.LayerNorm(bins)
        self.dropout3 = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        self.enc_attn2 = MultibandFrameAttention(num_bands, bins, cropsize)
        self.norm5 = nn.LayerNorm(bins)
        self.dropout4 = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        self.conv3 = nn.Linear(bins, feedforward_dim * 2, bias=bias)
        self.swish = nn.SiLU(inplace=True)
        self.conv4 = nn.Linear(feedforward_dim * 2, bins, bias=bias)
        self.norm6 = nn.LayerNorm(bins)
        self.dropout5 = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def __call__(self, x, mem):
        x = self.in_project(x.transpose(1,3)).squeeze(3)
        mem = self.mem_project(mem.transpose(1,3)).squeeze(3)

        x = torch.square(self.relu(self.in_norm(x)))
        mem = torch.square(self.relu(self.mem_norm(mem)))

        hs = self.self_attn1(x)
        hm = self.enc_attn1(x, mem=mem)
        x = self.norm1(x + self.dropout1(hs + hm))

        hL = torch.square(self.relu(self.conv1L(x.transpose(1,2)).transpose(1,2)))
        hR = self.conv1R(x.transpose(1,2)).transpose(1,2)
        h = self.norm2(hL + F.pad(hR, (0, hL.shape[2]-hR.shape[2])))

        h = self.dropout2(self.conv2(h.transpose(1,2)).transpose(1,2))
        x = self.norm3(x + h)

        h = self.dropout3(self.self_attn2(x))
        x = self.norm4(x + h)

        h = self.dropout4(self.enc_attn2(x, mem=mem))
        x = self.norm5(x + h)

        h = self.conv3(x)
        h = self.swish(h)
        h = self.dropout5(self.conv4(h))
        x = self.norm6(x + h)
                
        return x.transpose(1, 2).unsqueeze(1)

class MultibandFrameAttention(nn.Module):
    def __init__(self, num_bands, bins, cropsize):
        super().__init__()

        self.num_bands = num_bands
        self.q_proj = nn.Linear(bins, bins)
        self.q_conv = nn.Conv1d(bins, bins, kernel_size=3, padding=1, groups=bins)

        self.k_proj = nn.Linear(bins, bins)
        self.k_conv = nn.Conv1d(bins, bins, kernel_size=3, padding=1, groups=bins)

        self.v_proj = nn.Linear(bins, bins)
        self.v_conv = nn.Conv1d(bins, bins, kernel_size=3, padding=1, groups=bins)

        self.o_proj = nn.Linear(bins, bins)

        self.er = nn.Parameter(torch.empty(bins // num_bands, cropsize))
        nn.init.normal_(self.er)

    def forward(self, x, mem=None):
        b,w,c = x.shape
        q = self.q_conv(self.q_proj(x).transpose(1,2)).transpose(1,2).reshape(b, w, self.num_bands, -1).permute(0,2,1,3)
        k = self.k_conv(self.k_proj(x if mem is None else mem).transpose(1,2)).transpose(1,2).reshape(b, w, self.num_bands, -1).permute(0,2,3,1)
        v = self.v_conv(self.v_proj(x if mem is None else mem).transpose(1,2)).transpose(1,2).reshape(b, w, self.num_bands, -1).permute(0,2,1,3)
        p = F.pad(torch.matmul(q,self.er), (1,0)).transpose(2,3)[:,:,1:,:]
        qk = (torch.matmul(q,k)+p) / math.sqrt(c)
        a = F.softmax(qk, dim=-1)
        a = torch.matmul(a,v).transpose(1,2).reshape(b,w,-1)
        o = self.o_proj(a)
        return o

class FrameConv(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, activate=nn.LeakyReLU, norm=True):
        super(FrameConv, self).__init__()

        self.body = nn.Sequential(
            nn.Conv2d(
                in_channels, out_channels,
                kernel_size=(kernel_size, 1),
                stride=(stride, 1),
                padding=(padding, 0),
                dilation=(dilation, 1),
                groups=groups,
                bias=False),
            nn.BatchNorm2d(out_channels),
            activate(inplace=True))

    def __call__(self, x):
        h = self.body(x)

        return h