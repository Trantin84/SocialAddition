import world
import torch
import torch.nn as nn

import numpy as np
#import torch
#import torch.nn as nn
import torch.nn.functional as F


from torch_geometric.nn import GATConv
from torch_geometric.nn import GraphConv


class PureBPR(nn.Module):
    def __init__(self, config, dataset):
        super(PureBPR, self).__init__()
        self.num_users = dataset.n_users
        self.num_items = dataset.m_items
        self.latent_dim = config['latent_dim_rec']
        self.f = nn.Sigmoid()
        self.__init_weight()

    def __init_weight(self):
        self.embedding_user = torch.nn.Embedding(
            num_embeddings=self.num_users, embedding_dim=self.latent_dim)
        self.embedding_item = torch.nn.Embedding(
            num_embeddings=self.num_items, embedding_dim=self.latent_dim)
        nn.init.normal_(self.embedding_user.weight, std=0.1)
        nn.init.normal_(self.embedding_item.weight, std=0.1)

        print("using Normal distribution initializer")

    def getUsersRating(self, users):
        users = users.long()
        users_emb = self.embedding_user(users)
        items_emb = self.embedding_item.weight
        scores = torch.matmul(users_emb, items_emb.t())
        return self.f(scores)

    def bpr_loss(self, users, pos, neg):
        users_emb = self.embedding_user(users.long())
        pos_emb = self.embedding_item(pos.long())
        neg_emb = self.embedding_item(neg.long())
        pos_scores = torch.sum(users_emb * pos_emb, dim=1)
        neg_scores = torch.sum(users_emb * neg_emb, dim=1)
        loss = torch.mean(nn.functional.softplus(neg_scores - pos_scores))
        reg_loss = (1 / 2) * (users_emb.norm(2).pow(2) +
                              pos_emb.norm(2).pow(2) +
                              neg_emb.norm(2).pow(2)) / float(len(users))
        return loss, reg_loss


class LightGCN(nn.Module):
    def __init__(self, config, dataset):
        super(LightGCN, self).__init__()
        self.config = config
        self.dataset = dataset
        self._init_weight()

    def _init_weight(self):
        self.num_users = self.dataset.n_users
        self.num_items = self.dataset.m_items
        self.latent_dim = self.config['latent_dim_rec']
        self.n_layers = self.config['layer']
        self.embedding_user = torch.nn.Embedding(
            num_embeddings=self.num_users, embedding_dim=self.latent_dim)
        self.embedding_item = torch.nn.Embedding(
            num_embeddings=self.num_items, embedding_dim=self.latent_dim)

        nn.init.normal_(self.embedding_user.weight, std=0.1)
        nn.init.normal_(self.embedding_item.weight, std=0.1)
        self.f = nn.Sigmoid()
        self.interactionGraph = self.dataset.getInteractionGraph()
        print(f"{world.model_name} is already to go")

    def computer(self):
        """
        propagate methods for lightGCN
        """
        users_emb = self.embedding_user.weight
        items_emb = self.embedding_item.weight
        all_emb = torch.cat([users_emb, items_emb])
        #   torch.split(all_emb , [self.num_users, self.num_items])
        embs = [all_emb]
        G = self.interactionGraph

        for layer in range(self.n_layers):
            all_emb = torch.sparse.mm(G, all_emb)
            embs.append(all_emb)
        embs = torch.stack(embs, dim=1)
        # print(embs.size())
        light_out = torch.mean(embs, dim=1)
        users, items = torch.split(light_out, [self.num_users, self.num_items])
        self.final_user, self.final_item = users, items
        return users, items

    def getUsersRating(self, users):
        all_users, all_items = self.final_user, self.final_item
        users_emb = all_users[users.long()]
        items_emb = all_items
        rating = self.f(torch.matmul(users_emb, items_emb.t()))
        return rating

    def getEmbedding(self, users, pos_items, neg_items):
        all_users, all_items = self.computer()
        users_emb = all_users[users]
        pos_emb = all_items[pos_items]
        neg_emb = all_items[neg_items]
        users_emb_ego = self.embedding_user(users)
        pos_emb_ego = self.embedding_item(pos_items)
        neg_emb_ego = self.embedding_item(neg_items)
        return users_emb, pos_emb, neg_emb, users_emb_ego, pos_emb_ego, neg_emb_ego

    def bpr_loss(self, users, pos, neg):
        (users_emb, pos_emb, neg_emb,
         userEmb0, posEmb0, negEmb0) = self.getEmbedding(users.long(), pos.long(), neg.long())
        reg_loss = (1 / 2) * (userEmb0.norm(2).pow(2) +
                              posEmb0.norm(2).pow(2) +
                              negEmb0.norm(2).pow(2)) / float(len(users))
        pos_scores = torch.mul(users_emb, pos_emb)
        pos_scores = torch.sum(pos_scores, dim=1)
        neg_scores = torch.mul(users_emb, neg_emb)
        neg_scores = torch.sum(neg_scores, dim=1)

        loss = torch.mean(torch.nn.functional.softplus(neg_scores - pos_scores))

        return loss, reg_loss

#########################
class NGCF(nn.Module):
    def __init__(self, config, dataset):
        super(NGCF, self).__init__()
        self.config = config
        self.dataset = dataset
        self._init_weight()

    def _init_weight(self):
        self.num_users = self.dataset.n_users
        self.num_items = self.dataset.m_items
        self.latent_dim = self.config['latent_dim_rec']
        self.n_layers = self.config['layer']
        self.embedding_user = torch.nn.Embedding(
            num_embeddings=self.num_users, embedding_dim=self.latent_dim)
        self.embedding_item = torch.nn.Embedding(
            num_embeddings=self.num_items, embedding_dim=self.latent_dim)

        nn.init.normal_(self.embedding_user.weight, std=0.1)
        nn.init.normal_(self.embedding_item.weight, std=0.1)
        self.f = nn.Sigmoid()
        self.interactionGraph = self.dataset.getInteractionGraph()
        
        ##### ADD WEIGHT ####
        initializer = nn.init.xavier_uniform_
      
        self.weight_dict = nn.ParameterDict()
        layers = [self.latent_dim] + [self.latent_dim] + [self.latent_dim]+ [self.latent_dim]
        for k in range(self.n_layers):
            self.weight_dict.update({'W_gc_%d'%k: nn.Parameter(initializer(torch.empty(layers[k],
                                                                      layers[k+1])))})
            self.weight_dict.update({'b_gc_%d'%k: nn.Parameter(initializer(torch.empty(1, layers[k+1])))})

            self.weight_dict.update({'W_bi_%d'%k: nn.Parameter(initializer(torch.empty(layers[k],
                                                                      layers[k+1])))})
            self.weight_dict.update({'b_bi_%d'%k: nn.Parameter(initializer(torch.empty(1, layers[k+1])))})

        print(f"{world.model_name} is already to go")

    def computer(self):
        """
        propagate methods for NGCF
        """
        users_emb = self.embedding_user.weight
        items_emb = self.embedding_item.weight
  #      all_emb = torch.cat([users_emb, items_emb])
 
########### CALCULATING 
        ego_embeddings = torch.cat([users_emb, items_emb], 0)
        all_emb = [ego_embeddings]
        A = self.interactionGraph
        for k in range(self.n_layers):
            side_embeddings = torch.sparse.mm(A, ego_embeddings)

            # transformed sum messages of neighbors.
            sum_embeddings = torch.matmul(side_embeddings, self.weight_dict['W_gc_%d' % k]) \
                                             + self.weight_dict['b_gc_%d' % k]

            # bi messages of neighbors.
            # element-wise product
            bi_embeddings = torch.mul(ego_embeddings, side_embeddings)
            # transformed bi messages of neighbors.
            bi_embeddings = torch.matmul(bi_embeddings, self.weight_dict['W_bi_%d' % k]) \
                                            + self.weight_dict['b_bi_%d' % k]

            # non-linear activation.
            ego_embeddings = nn.LeakyReLU(negative_slope=0.2)(sum_embeddings + bi_embeddings)

            # message dropout.
           # ego_embeddings = nn.Dropout(self.mess_dropout[k])(ego_embeddings)

            # normalize the distribution of embeddings.
            norm_embeddings = torch.nn.functional.normalize(ego_embeddings, p=2, dim=1)

            all_emb += [norm_embeddings]

        light_out = torch.cat(all_emb, 1)
        #light_out = torch.mean(embs, dim=1)

        #####################################


        #embs = torch.stack(embs, dim=1)
        # print(embs.size())
        
        #light_out = torch.mean(embs, dim=1)
        users, items = torch.split(light_out, [self.num_users, self.num_items])
        self.final_user, self.final_item = users, items
        return users, items

    def getUsersRating(self, users):
        all_users, all_items = self.final_user, self.final_item
        users_emb = all_users[users.long()]
        items_emb = all_items
        rating = self.f(torch.matmul(users_emb, items_emb.t()))
        return rating

    def getEmbedding(self, users, pos_items, neg_items):
        all_users, all_items = self.computer()
        users_emb = all_users[users]
        pos_emb = all_items[pos_items]
        neg_emb = all_items[neg_items]
        users_emb_ego = self.embedding_user(users)
        pos_emb_ego = self.embedding_item(pos_items)
        neg_emb_ego = self.embedding_item(neg_items)
        return users_emb, pos_emb, neg_emb, users_emb_ego, pos_emb_ego, neg_emb_ego

    def bpr_loss(self, users, pos, neg):
        (users_emb, pos_emb, neg_emb,
         userEmb0, posEmb0, negEmb0) = self.getEmbedding(users.long(), pos.long(), neg.long())
        reg_loss = (1 / 2) * (userEmb0.norm(2).pow(2) +
                              posEmb0.norm(2).pow(2) +
                              negEmb0.norm(2).pow(2)) / float(len(users))
        pos_scores = torch.mul(users_emb, pos_emb)
        pos_scores = torch.sum(pos_scores, dim=1)
        neg_scores = torch.mul(users_emb, neg_emb)
        neg_scores = torch.sum(neg_scores, dim=1)

        loss = torch.mean(torch.nn.functional.softplus(neg_scores - pos_scores))

        return loss, reg_loss

############ TIN CF #############
class SocialLGN(NGCF):
    def _init_weight(self):
        super(SocialLGN, self)._init_weight()
        self.socialGraph = self.dataset.getSocialGraph()
        self.Graph_Weight = Graph_Weight(self.latent_dim)

    def computer(self):
        users_emb = self.embedding_user.weight
        items_emb = self.embedding_item.weight
        all_emb = torch.cat([users_emb, items_emb])
        A = self.interactionGraph
        S = self.socialGraph
        
        embs = [all_emb]
        for k in range(self.n_layers):


            # embedding from last layer
            users_emb, items_emb = torch.split(all_emb, [self.num_users, self.num_items])
            # social network propagation(user embedding)
            users_emb_social = torch.sparse.mm(S, users_emb)
            # user-item bi-network propagation(user and item embedding)
            all_emb_interaction = torch.sparse.mm(A, all_emb)
                        # transformed sum messages of neighbors.
            #all_emb_interaction = torch.matmul(all_emb_interaction, self.weight_dict['W_gc_%d' % k]) \
            #                                 + self.weight_dict['b_gc_%d' % k]
            # get users_emb_interaction
            users_emb_interaction, items_emb_next = torch.split(all_emb_interaction, [self.num_users, self.num_items])
            new_emb = torch.cat([users_emb_social, items_emb_next])
            # graph fusion model
            all_emb = self.Graph_Weight(all_emb_interaction, new_emb)
            
            embs.append(all_emb)
        embs = torch.stack(embs, dim=1)
        final_embs = torch.mean(embs, dim=1)
        users, items = torch.split(final_embs, [self.num_users, self.num_items])
        self.final_user, self.final_item = users, items
        return users, items

class Graph_Weight(nn.Module):
    def __init__(self, embed_dim):
        super(Graph_Weight, self).__init__()
        self.att_x = nn.Linear(embed_dim, embed_dim, bias=True)
        self.att_y = nn.Linear(embed_dim, embed_dim, bias=True) 
        self.att_z = GraphConv(embed_dim, embed_dim, bias=True) 
        self.comb = nn.Linear(embed_dim * 2, embed_dim)

    def forward(self, x, y, edge_index, edge_weight=None):
        h1 = torch.tanh(self.att_x(x))
        h2 = torch.tanh(self.att_z(y))
        output = self.comb(torch.cat((h1, h2), dim=1))
        output = output / output.norm(2)
        return output


    
############### OLD SOCIAL #####################
class OLDSocialLGN(NGCF):
    def _init_weight(self):
        super(SocialLGN, self)._init_weight()
        self.socialGraph = self.dataset.getSocialGraph()
        self.Graph_Comb = Graph_Comb(self.latent_dim)

    def computer(self):
        users_emb = self.embedding_user.weight
        items_emb = self.embedding_item.weight
        all_emb = torch.cat([users_emb, items_emb])
        A = self.interactionGraph
        S = self.socialGraph
        embs = [all_emb]
        for layer in range(self.n_layers):
            # embedding from last layer
            users_emb, items_emb = torch.split(all_emb, [self.num_users, self.num_items])
            # social network propagation(user embedding)
            users_emb_social = torch.sparse.mm(S, users_emb)
            # user-item bi-network propagation(user and item embedding)
            all_emb_interaction = torch.sparse.mm(A, all_emb)
            # get users_emb_interaction
            users_emb_interaction, items_emb_next = torch.split(all_emb_interaction, [self.num_users, self.num_items])
            # graph fusion model
            users_emb_next = self.Graph_Comb(users_emb_social, users_emb_interaction)
            all_emb = torch.cat([users_emb_next, items_emb_next])
            embs.append(all_emb)
        embs = torch.stack(embs, dim=1)
        final_embs = torch.mean(embs, dim=1)
        users, items = torch.split(final_embs, [self.num_users, self.num_items])
        self.final_user, self.final_item = users, items
        return users, items

#################################################################

class Graph_Comb(nn.Module):
    def __init__(self, embed_dim):
        super(Graph_Comb, self).__init__()
        self.att_x = nn.Linear(embed_dim, embed_dim, bias=False)
        self.att_y = nn.Linear(embed_dim, embed_dim, bias=False)
        self.comb = nn.Linear(embed_dim * 2, embed_dim)

    def forward(self, x, y):
        h1 = torch.tanh(self.att_x(x))
        h2 = torch.tanh(self.att_y(y))
        output = self.comb(torch.cat((h1, h2), dim=1))
        output = output / output.norm(2)
        return output
