# vocal-remover

This is a deep-learning-based tool to extract instrumental track from your songs.

Currently testing out yet another new architecture. The current architecture can be found in frame_transformer.py in the root directory, everything but the rotary embeddings are found in that file. The nueral network consists of a residual u-net where the encoders are defined as frame_transformer_encoder(frame_encoder(x)), and the decoders are defined as frame_transformer_decoder(frame_decoder(x, skip), skip). The neural network is no longer a convolutional neural network, but rather uses a mix of position-wise and depth-wise linear transformations. Update: This pure transformer neural network does learn to remove vocals, however currently at 84k optimization steps it is not quite as good as I'd like (it removes most but you can hear noise where it removed vocals). I do find myself curious to see if this gets better later on in training, though. Almost worried its overfitting as training loss is steadily dropping... perhaps adding dropout to the frame encoder and frame decoder would be called for given that they use fully connected layers now.

FrameEncoder and FrameDecoder now use a module called MultichannelLinear; this module allows each channel to learn its own position-wise linear layer which is is used for each frame. The module also includes an optional depth-wise component which is utilized in the frame encoder and frame decoder to change the number of channels. All activation functions use GELU currently, and all normalization uses LayerNorm on individual frames of each channel. The frame transformer encoder uses the pre-norm transformer encoder architecture with GELU acvtivation. They use a variant of multihead attention that I call multichannel multihead attention which adds a channel dimension to the multihead attention mechanism to allow for each channel to have its own heads and batch attention calculations. Each projection in the multichannel multihead attention makes use of the MultichannelLinear layer to allow each channel to learn its own projection. The feedforward portion of the frame transformer encoder also makes use of the multichannel linear module. The frame transformer decoder module is the same, however it uses the residual u-nets skip connection for the cross attention. It starts off a fair amount worse, but it catches up fairly quickly and shaves off over 2 hours from training with even more parameters. If it catches up to the convolutional variant then it seems like an obvious choice given its speed on gpu.

**Update 8/17/22**

Architecture has taken yet another fairly large turn. Current architecture consists of a residual u-net with the encoders defined as frame_primer_encoder(frame_encoder(x)) and the decoder defined as frame_primer_decoder(frame_decoder(x, skip), skip). Frame primer encoders use the primer encoder architecture; like in more typical transformers, position-wise linear layers are used. Where this deviates is that the position-wise linear layers are applied to each frame of each channel; the primer blocks also make use of multichannel multihead attention which is multi-dconv-head attention applied to each channel using a 5th channel dimension vs the typical 4d tensor used in multihead attention for the matrix multiplication. Frame primer decoders use the primer decoder architecture, however for memory it utilizes the u-net's skip connection. Frame encoders and frame decoders both utilize residual blocks for their core body; in my current tests I use just 1 although this is a hyperparameter that can be increased. Each of the residual blocks use frame convolutions rather than typical convolutions. Frame convolutions use layer normalization and normalize each frame individually; from here, they use Nx1 kernels for the convolution. Frame convolutions first collapse the width dimension into the batch dimension and unsqueeze the last dimension to make use of the fact that information doesn't transfer between frames in the frame convolution process.

Repo has been updated to use multichannel linear layers within the multichannel multihead attention module as well as in the frame primer modules. This allows each channel to learn its own position-wise linear layer for the feedforward layers and projections (module uses a 3d weight tensor and batched matrix multiplication via matmul). So far it seems to be doing quite well, however I need to train it further to assess just how well it does. Should be obvious but this repo is not in a usable state and is basically just my general purpose experiment repo, will probably create a new fork once I'm happy with this one with the intention of changing code only through PRs and making things user friendly with pretrained checkpoints of various sizes.

--

This architecture is what I'm calling a frame primer. In comparison with the original repo there are many differences, however the most apparent will be the use of a variant of the primer architecture (a transformer variant) as well as a single residual u-net that only downsamples on one dimension. Each encoder and decoder in the residual u-net is followed by either a frame primer encoder or a frame primer decoder. Frame primer modules extract a specified number of channels from the convolutional feature maps and then calculates attention in parallel; I call this form of attention "multichannel multihead attention." These attention modules use rotary positional embeddings. The resulting attention maps are then concatenated with the input as the single LSTM channel in MMDENSELSTM and is then sent through to the next layer of the residual u-net. Frame primer decoders, instead of making use of memory from a sequence of encoders, makes use of the skip connection in the residual u-net which includes the attention maps from the corresponding frame primer encoder. All normalization layers also use layer norm; for convolutional blocks this means reshaping to [B,W,H\*C] and normalizing H\*C. The convolutional encoders and decoders use what I call column convolutions which serves two purposes: 1) to prevent information from leaking between frames outside of the frame primer modules and 2) to make use of optimizations that are only possible with column convolutions which are far faster than Conv2d for kernel sizes greater than 1 (same architecture using frame conv vs conv2d is over 1.5 hours faster to train on an RTX 3080 Ti). From testing, this architecture appears to work better than the convolutional variant when you have access to large amounts of data which is where the next piece of this repo comes into play. I make use of an augmentation technique that I unoriginally call voxaug, though with image processing this is pretty common I think. I have a large collection of instrumental songs along with 1200+ vocal tracks and have the dataloader randomly mix and match pieces of these tracks to create data on the fly which ensures that all mix tracks will be a perfect sum of instruments + vocals. While this doesn't seem to have a drastic impact on validation loss below, it allows for the model to learn far more nuance and for instance avoid being tripped up by instruments like fretless bass which seem to pose a challenge for most architectures (the below checkpoint with the current inference code typically has no issue with fretless bass at all).

Current training has been paused, I have a teaser checkpoint here: https://mega.nz/file/m45HmLJZ#J8eQqrI1zJcUvX8Imyu8OTF_YeOnjd5FRVOxIMIz91M - this is at the 12th mini epoch, so it would have seen the full dataset at most 3 times (though really far less with augmentations). I did notice a few notes partially removed when listening to music with fretless bass and have since purchased 5 solo bass albums that feature fretless bass to alleviate this issue; I will be continuing training from this checkpoint but resetting the learning rate decay so that it has a chance to see the new material with its highest learning rate. Hyperparameters for this model are: { channels = 16, num_bands=[16, 16, 16, 8, 4, 2], bottlenecks=[1, 2, 4, 8, 12, 14], feedforward_dim = 12288, dropout 0.1, cropsize 512, adam, no amsgrad, no weight decay, max learning rate of 1e-4, num_res_blocks = 1 }.

**NOTE ON ABOVE CHECKPOINT** 
The above checkpoint is fairly outdated at this point and subpar to my current checkpoint I'm using for youtube videos. I have restarted training one more time with about 40 new vocal tracks for the voxaug dataset and multiple albums worth of new instrumental music. For this training I have decided to simply force vocal augmentations and validation loss actually seems to be doing extremely well. Forcing vocal augmentations ensures that the model will have perfect training data, so this seems ideal. As absurd as it sounds I've skimmed through all the songs in my instrumental dataset and at this point am confident the dataset is pristine. Unfortunately I cannot share my dataset as I have built it over time mainly by purchasing stuff off of bandcamp in an attempt to also help support artists, but I will share checkpoints along the way to fully training. Once the supervised training session is complete I will switch to pretraining; the instrumentals are already extremely high quality so I'm not sure how helpful it'll be for that but I have quite a few ideas for a pretrained audio neural network like this.

Still working on comparing this fork to the original repo. This current graph shows four runs: ![image](https://user-images.githubusercontent.com/30326384/183276706-242271c0-b519-4349-9d71-1cbaa10d2589.png)

Run details:

drawn-mountain-926 is a run on my full dataset with the frame primer architecture 118,155,192 parameters FramePrimer2(channels=16, feedforward_dim=12288, n_fft=2048, dropout=0.1, num_res_blocks=1, num_bands=[16, 16, 16, 8, 4, 2], bottlenecks=[1, 2, 4, 8, 12, 14])

pleasant-gorge-925 is tsurumeso's architecture that obviously heavily heavily inspired mine. 129,170,978 parameters - CascadedNet(args.n_fft, 96, 512)

smaller dataset tests:
silvery-butterfly-923 is my architecture on a small subset of the dataset (768 songs I think).

logical-thunder-922 is tsurumeso's architecture on a small subset of the dataset as above

Validation loss is actually quite similar between the two architectures with the frame primer doing better on the full dataset while tsurumeso's architecture does better on a smaller dataset. The validation loss for both architectures is dropping at an equal rate currently on the larger dataset, will need to take training further with both however after 33,243K batches the frame primer is currently doing marginally better than a large version of the cascade net. Given the difference in output between the two architectures, this seems to imply that a combination of the two would produce the best results.

After I finsih training further, I will start on a full pretraining session using the frame primer architecture. Given that it seems to do better with much more data, pretraining should unlock even more potential. I find myself curious about applying this architecture to images as well, as you could simply have vertical and horizontal column attention at that point which would be far cheaper than attention between each individual feature and would allow to extract multiple channels like this. Could simply have two frame (column?) primers after each encoder for a horizontal and vertical attention pass. Might even be useful here...

## References
- [1] Jansson et al., "Singing Voice Separation with Deep U-Net Convolutional Networks", https://ismir2017.smcnus.org/wp-content/uploads/2017/10/171_Paper.pdf
- [2] Takahashi et al., "Multi-scale Multi-band DenseNets for Audio Source Separation", https://arxiv.org/pdf/1706.09588.pdf
- [3] Takahashi et al., "MMDENSELSTM: AN EFFICIENT COMBINATION OF CONVOLUTIONAL AND RECURRENT NEURAL NETWORKS FOR AUDIO SOURCE SEPARATION", https://arxiv.org/pdf/1805.02410.pdf
- [4] Liutkus et al., "The 2016 Signal Separation Evaluation Campaign", Latent Variable Analysis and Signal Separation - 12th International Conference
- [5] Vaswani et al., "Attention Is All You Need", https://arxiv.org/pdf/1706.03762.pdf
- [6] So et al., "Primer: Searching for Efficient Transformers for Language Modeling", https://arxiv.org/pdf/2109.08668v2.pdf
- [7] Su et al., "RoFormer: Enhanced Transformer with Rotary Position Embedding", https://arxiv.org/abs/2104.09864
- [8] Asiedu et all., "Decoder Denoising Pretraining for Semantic Segmentation", https://arxiv.org/abs/2205.11423
