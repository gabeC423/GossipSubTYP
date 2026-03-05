#Libraries:
from typing import Counter

import numpy as np
import simpy
import random
from config import *
import matplotlib.pyplot as plt
import math
import seaborn as sns
import pandas as pd
import sqlite3
from scipy.stats import linregress
#Database handling:
conn = sqlite3.connect("results.db")
cursor = conn.cursor()

# cursor.execute("DROP TABLE IF EXISTS simulation_results")
# conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS simulation_results (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               experiment TEXT,
               run INTEGER,
               hash_rate INTEGER,
               block_id INTEGER,
               confirmation_time REAL,
               block_creation_time REAL,
               block_size INTEGER,
               height INTEGER,
               creator_id INTEGER,
               network_size INTEGER,
               number_of_forks INTEGER
)
""")

conn.commit()

#Global variables:
env = simpy.Environment()
nodes = []
current_block_id = 0
current_node_id = 0
proposer_nodes = []
created_blocks = []
discarded_blocks = []
blocks_kept = []
run = 0

#Datasets:
block_creation_time = {}

#------------------------------------------------------------------------------------#
                     #MESSAGE CLASSES:
#Message class, defines structure of a message:
class Message:
    def __init__(self, block_id, sender_id, creation_time, height, creator, parent = None):
        #Set parent:
        if parent != None:
            self.parent = parent
        else:
            self.parent = None

        #Message attributes:
        self.block_id = block_id
        self.size = block_size
        self.sender_id = sender_id
        self.creation_time = creation_time
        self.height = height
        self.creator = creator

#'I have' message class:
class IHaveMessage:
    def __init__(self, sender_id, creation_time, advertised_block_id):
        self.sender_id = sender_id
        self.creation_time = creation_time
        self.advertised_block_id = advertised_block_id
        self.size = i_have_want_size

#'I want' message class:
class IWantMessage():
    def __init__(self, sender_id, creation_time, requested_block_id):
        self.sender_id = sender_id
        self.creation_time = creation_time
        self.requested_block_id = requested_block_id
        self.size = i_have_want_size

#------------------------------------------------------------------------------------#
                        #NODE CLASS AND METHODS:
#Node class, defines structure of a node:
class Node:
    def __init__(self, env, initial_end_chain, hashrate):
        #Set Node ID:
        global current_node_id
        current_node_id += 1

        #Node attributes:
        self.bandwidth = bandwidth
        self.neighbours = []
        self.node_id = current_node_id
        self.inbox = simpy.Store(env)
        self.seen_blocks = set()
        self.log = []
        self.env = env
        self.metrics = {}
        self.end_of_chain_block = initial_end_chain
        self.blocks = {}
        self.chain_ends = set()
        self.peer_degree_met = False
        self.hashrate = hashrate
        self.mining_height = 0
        
        #Add initial block to the chain ends:
        self.chain_ends.add(initial_end_chain)
        env.process(self.run())

    #Method to add a neighbour:
    def add_neighbour(self, neighbour):
        global peer_degree

        #Checks that the amount of neighbours a node has does not exceed the peer degree:
        if len(self.neighbours) < peer_degree:
            #Adds a new neighbour and locally logs this event as successful:
            self.neighbours.append(neighbour)

            #Debug:
            #log_message = self.env.now, "Added new neighbour: " + str(neighbour.node_id)
            #self.log.append(log_message)
        #else:
            #If the peer degree condition is not met then the node locally logs the event as unsuccessful.
            # log_message = self.env.now, "Neighbour list has hit peer degree, could not add node: " + str(neighbour.node_id)
            # self.log.append(log_message)

    #Run method:
    def run(self):
        while True:
            message = yield self.inbox.get()

            if isinstance(message, Message):
                #Checks that the node has not already received this block:
                if message.block_id not in self.seen_blocks and (message.parent is None or message.parent in self.blocks.values()):
                    #Marks block as seen, now that it has received it:
                    self.seen_blocks.add(message.block_id)
                    self.blocks[message.block_id] = message

                    if message.height == self.mining_height and self.mine_process is not None:
                        self.mine_process.interrupt()
                        self.mine_process = None


                    #Create 'I have' message for the received block:
                    i_have_message = IHaveMessage(self.node_id, self.env.now, message.block_id)
                    self.env.process(self.send_message(i_have_message))
                    
                    #Debug:
                    # #Locally logs that an 'I have' message was sent to all neighbours:
                    # log_message = self.env.now, "'I have' message for block: " + str(i_have_message.advertised_block_id) + " was sent to all neighbours."
                    # self.log.append(log_message)

                    #Checks if the block's parent exists and is an end of a chain:
                    if message.parent is not None:
                        self.chain_ends = {end for end in self.chain_ends if end.block_id != message.parent.block_id}

                    #Set current block as new chain end:
                    self.chain_ends.add(message)

                    # #Debug:
                    # #Locally logs this event as successful:
                    # log_message = self.env.now, "Received block: " + str(message.block_id)
                    # self.log.append(log_message)
                    
                    #Locally Records the time the node received the block:
                    self.metrics[message.block_id] = self.env.now
                    
                #Debug:
                # elif message.parent is not None and message.parent not in self.blocks.values():
                #     log_message = "Block: " + str(message.block_id) + " is an orphan, message discarded."
                #     self.log.append(log_message)
                #Debug:
                # else:
                #     #If block has already been received, node locally logs this event as unsucessful:
                #     log_message = self.env.now, "Block has already been received by this node: " + str(message.block_id)
                #     self.log.append(log_message)
            #Handles if the received message is of type: 'I have':
            elif isinstance(message, IHaveMessage):
                #Debug:
                # #Locally logs that this node received an 'I have' message:
                # log_message = self.env.now, "'I have' message received from node: " + str(message.sender_id)
                # self.log.append(log_message)

                #Decides whether the node wants to request the advertised block, this is decided by whether it has seen the advertised block before:
                if message.advertised_block_id not in self.seen_blocks:
                    i_want_message = IWantMessage(self.node_id, self.env.now, message.advertised_block_id)
                    recipient = self.get_node_from_id(message.sender_id)
                    
                    #Sends the 'I want' message:
                    if recipient is not None:
                        yield self.env.process(self.send_message(i_want_message, recipient))

                        #Debug:
                        # #Locally logs that this node has sent an 'I have' message to the node who sent the 'I want' message:
                        # log_message = self.env.now, "'I want' message sent to: " + str(message.sender_id)
                        # self.log.append(log_message)
            #Handles if the received message is of type: 'I want':
            elif isinstance(message, IWantMessage):
                #Debug:
                # #Locally logs that this node received an 'I want' message:
                # log_message = self.env.now, "'I want' message received from node: " + str(message.sender_id)
                # self.log.append(log_message)

                if message.requested_block_id in self.blocks:
                    requested_block = self.blocks[message.requested_block_id]
                    recipient = self.get_node_from_id(message.sender_id)

                    if recipient is not None:
                        yield self.env.process(self.send_message(requested_block, recipient))

                        #Locally logs the sending of the requested block to the node requesting it:
                        log_message = self.env.now, "Requested block sent to node: " + str(message.sender_id)
                        self.log.append(log_message)
                    
    #Get a node from its ID:
    def get_node_from_id(self, node_id):
        for node in nodes:
            if node.node_id == node_id:
                return node
        return None
    
    #Helper method for sendning a block to a single node:
    def send_single_node_message(self, message, neighbour):
        #Calculates send delay:
        send_delay = message.size / self.bandwidth

        yield neighbour.env.timeout(send_delay)
        yield neighbour.inbox.put(message)

    def create_block(self):
        global current_block_id
        #Stores current longest chain end:
        current_best_end = None

        #Finds the chain end of the longest chain (best chain):
        for end in self.chain_ends:
            if current_best_end == None or end.height > current_best_end.height:
                current_best_end = end
        
        current_block_id += 1

        #Creates block and sets it's parent as the best chain end:
        block = Message(current_block_id, self.node_id, self.env.now, current_best_end.height + 1, self.node_id, current_best_end)
        block_creation_time[block.block_id] = self.env.now

        #Create 'I have' for created block:
        i_have_message = IHaveMessage(self.node_id, self.env.now, block.block_id)
        self.env.process(self.send_message(i_have_message))

        #Locally logs that an 'I have' message was sent to all neighbours:
        log_message = self.env.now, "'I have' message for block: " + str(i_have_message.advertised_block_id) + " was sent to all neighbours."
        self.log.append(log_message)

        self.end_of_chain_block = block
        self.seen_blocks.add(block.block_id)
        self.blocks[block.block_id] = block
        self.chain_ends.remove(current_best_end)
        self.chain_ends.add(block)

        #Locally log creation of block:
        log_message = self.env.now, "Created block: " + str(block.block_id)
        self.log.append(log_message)
        
        #Update metrics:
        self.metrics[block.block_id] = self.env.now
        self.env.process(self.send_message(block))

        return block
    
    #Method for sending blocks and messages:
    #Chat GPT helped with this function.
    def send_message(self, message, recipient_id = None):
        active_nodes = []
        queue = list(self.neighbours)

        if recipient_id == None:
            while queue or active_nodes:
                while len(active_nodes) < max_parallel_nodes and queue:
                    neighbour = queue.pop(0)
                    process = self.env.process(self.send_single_node_message(message, neighbour))
                    active_nodes.append(process)

                if active_nodes:
                    yield simpy.events.AnyOf(self.env, active_nodes)

                active_nodes = [p for p in active_nodes if not p.triggered]
        else:
            yield self.env.process(self.send_single_node_message(message, recipient_id))

#------------------------------------------------------------------------------------#
                    #PROGRAM FUNCTIONS:

def get_node(node_id):
    for node in nodes:
        if node.node_id == node_id:
            return node
    return None


#Generates a hashrate for a node randomly:
def generate_hashrate():
    r = random.random()
    if r < 0.05:        # top 5% of nodes (10 nodes)
        return random.randint(50, 100)  # high-power miners
    else:               # remaining 95% of nodes
        return random.randint(1, 5)     # low-power m


        
def instantiate_nodes():
    for i in range(number_of_nodes):
        hashrate = generate_hashrate()
        new_node = Node(env, start_block, hashrate)
        new_node.blocks[start_block.block_id] = start_block
        nodes.append(new_node)

#Creates network layout for nodes:
def create_topology():
    for node in nodes:
        available_nodes = []

        #Ensures that available nodes to be added as neighbours have not already met peer degree:
        for n in nodes:
            if n.peer_degree_met == False and n != node:
                available_nodes.append(n)

        #Prevent infinite loop if not enough available nodes
        while len(node.neighbours) < peer_degree and available_nodes:  

            proposed_peer = random.choice(available_nodes)
            available_nodes.remove(proposed_peer)

            node.add_neighbour(proposed_peer)

            #Make connection bidirectional so both nodes count the neighbour
            proposed_peer.add_neighbour(node)  
        
        #Checks if peer degree is met:
        if len(node.neighbours) >= peer_degree:
            node.peer_degree_met = True

        #Locally logs that neighbour was added:
        log_message = node.env.now, "Added neighbours: " +str([n.node_id for n in node.neighbours])
        node.log.append(log_message)



#Calculates consensus for a block:
def calculate_consenus_time(block):
    highest_time = None
    consensus_met = True
    consensus_time = None
    nodes_met = 0
    
    for node in nodes:
        current_depth = 0
        current_greatest_end = None

        #Checks each fork:
        for end in node.chain_ends:
            if current_greatest_end == None:
                current_greatest_end = end
            #Checks to see which is longest chain:
            elif end.height > current_greatest_end.height:
                current_greatest_end = end
        
        current_ancestor = current_greatest_end

        #Traverses chain:
        while current_ancestor != None:
            if current_ancestor.block_id != block.block_id:
                #Increments depth:
                current_depth += 1

                if current_ancestor.parent != None:
                    current_ancestor = current_ancestor.parent
                #Break out of loop if chain has fully been traversed:
                else:
                    consensus_met = False
                    break
            #Consensus is met if confirmation depth is satisfied:
            elif current_ancestor == block:
                if current_depth >= confirmation_depth:
                    #Amount of nodes met consensus is incremented:
                    nodes_met += 1

                #Update new highest time:
                if highest_time is None or node.metrics[block.block_id] > highest_time:
                    highest_time = node.metrics[block.block_id]

                #Exit loop:
                break
            
    #Calculate time consensus was met:
    if nodes_met /len(nodes) >= 0.51:
        consensus_time = highest_time - block.creation_time
    #'None' output used to determine that consensus was not met:
    else:
        consensus_time = None
    
    return consensus_time

#Calculates how many forks there are in the simulation:
def get_number_forks():
    forks = set()

    #Finds forks in each node:
    for node in nodes:
        for end in node.chain_ends:
            forks.add(end.block_id)

    return len(forks) - 1

#Calculate wait interval:
def wait_time(hashrate_i, total_hashrate):
    share = hashrate_i / total_hashrate
    lam = share * lambda_NET
    u = random.random()
    return -math.log(u) / lam

#Function allowing for repeated dynamic selection of proposal nodes based on hash-rate:
def mining(node):
    while True:
        current_greatest_end = None
        #Checks each fork:
        for end in node.chain_ends:
            if current_greatest_end == None or end.height > current_greatest_end.height:
                current_greatest_end = end
            #Checks to see which is longest chain:
            elif end.height > current_greatest_end.height:
                current_greatest_end = end
        
        height = current_greatest_end.height
        node.mining_height = height + 1

        wait_interval = wait_time(node.hashrate, total_hashrate)

        try:
            yield env.timeout(wait_interval)
            created_blocks.append(node.create_block())
            node.mining_height = 0
        except simpy.Interrupt:
            node.log.append((env.now, f"Mining cancelled at height {node.mining_height}"))
            node.mining_height = 0


#Finds total hash-rate of network:
def calculate_total_hashrate():
    total_hashrate = 0

    for node in nodes:
        total_hashrate += node.hashrate

    return total_hashrate
      
#------------------------------------------------------------------------------------#               
                            #INITIALISATION:

#Genesis block:
start_block = Message(current_block_id, sender_id = None, creation_time = 0, height = 0, creator = None, parent = None)

#Set up network:
instantiate_nodes()
create_topology()

total_hashrate = calculate_total_hashrate()

def run_simulation(experiment):
    #Starts mining for each node:
    for node in nodes:
        node.mine_process = env.process(mining(node))

    #Start simulation:
    env.run(until = simulation_time)
    inter_arrivals = np.diff(sorted([b.creation_time for b in created_blocks]))

    #Display node logs:
    for node in nodes:
        print(f"Node {node.node_id} log:")
        for entry in node.log:
            print(entry)
        print()

    forks = get_number_forks()

    #Calculate consensus time:
    for block in created_blocks:
        consensus_time = calculate_consenus_time(block)
        creator = get_node(block.creator)
        creator_hashrate = creator.hashrate

        #Consensus output:
        if consensus_time == None:
            print("BLOCK: " + str(block.block_id) + "CONSENSUS WAS NOT MET BEFORE DEADLINE.")
            discarded_blocks.append(block.block_id)
        elif consensus_time > consensus_deadline:
            print("BLOCK: " + str(block.block_id) + "CONSENSUS MET BUT DEADLINE EXCEEDED BY: " + str(consensus_time - consensus_deadline))
            blocks_kept.append(block)
        elif consensus_time == consensus_deadline:
            print("BLOCK: " + str(block.block_id) + "CONSENSUS DEADLINE MET.")
            blocks_kept.append(block)
        else:
            print("BLOCK: " + str(block.block_id) + "CONSENSUS ACHIEVED BEFORE DEADLINE, TIME REMAINING BEFORE DEADLINE: " + str(consensus_deadline - consensus_time))
            blocks_kept.append(block)
        
        cursor.execute("""
                       INSERT INTO simulation_results
                       (experiment, run, hash_rate, block_id, confirmation_time, block_creation_time, block_size, height, creator_id, network_size, number_of_forks)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """, (
                       experiment,
                       run,
                       creator_hashrate,
                       block.block_id,
                       consensus_time,
                       block.creation_time,
                       block.size,
                       block.height,
                       block.creator,
                       len(nodes),
                       forks
                    ))
        conn.commit()


            # Count blocks per creator
    blocks_per_node = Counter([b.creator for b in created_blocks])

    # Convert to sorted lists for plotting
    node_ids = sorted(blocks_per_node.keys())  # numeric node IDs
    block_counts = [blocks_per_node[n] for n in node_ids]

    print("Forks: " + str(forks))

    fork_rate = (forks / len(created_blocks)) * 100
    print(fork_rate)

    mean_block_interval = simulation_time/len(created_blocks)
    print(mean_block_interval)

cursor.execute("SELECT MAX(run) FROM simulation_results WHERE experiment='Equal Hash'")
last_run = cursor.fetchone()[0] or 0
run = last_run + 1

run_simulation("-")

# #Inter block 
# df = pd.read_sql_query("""
#     SELECT run, block_creation_time
#     FROM simulation_results
#     WHERE experiment = 'Normal Run'
#     ORDER BY run, block_creation_time
# """, conn)

# all_inter_arrivals = []

# # Group by each run
# for run_id, group in df.groupby("run"):
#     times = group['block_creation_time'].sort_values().to_numpy()
#     if len(times) > 1:
#         inter_arrivals = np.diff(times)
#         all_inter_arrivals.extend(inter_arrivals)


# sns.histplot(all_inter_arrivals, bins=20)
# plt.xlabel("Inter-arrival Time")
# plt.ylabel("Number of Blocks")
# plt.title("Block Inter-arrival Times Across All Runs")
# plt.show()

# #Equal hash rate block share:

# df = pd.read_sql_query("""
#     SELECT run, creator_id, block_id
#     FROM simulation_results
#     WHERE experiment = 'Equal Hash Rate'
# """, conn)

# # Count blocks per node per run
# blocks_per_node_run = df.groupby(['run', 'creator_id']).count()['block_id'].reset_index()
# blocks_per_node_run.rename(columns={'block_id':'blocks_created'}, inplace=True)

# # Compute mean and std of blocks per node across runs
# stats = blocks_per_node_run.groupby('creator_id')['blocks_created'].agg(['mean','std']).reset_index()

# # Plot bar chart with error bars
# plt.figure(figsize=(10,6))
# plt.bar(stats['creator_id'], stats['mean'], yerr=stats['std'], color='skyblue', alpha=0.7, capsize=5, label='Mean ± Std Dev')

# # Fit linear trend line
# slope, intercept = np.polyfit(stats['creator_id'], stats['mean'], 1)
# best_fit = slope * stats['creator_id'] + intercept
# plt.plot(stats['creator_id'], best_fit, color='red', linestyle='--', label='Line of Best Fit')

# plt.xlabel("Node ID")
# plt.ylabel("Blocks Created")
# plt.title("Blocks per Node Across Multiple Runs — Equal Hash Rate")
# plt.legend()
# plt.grid(True)
# plt.show()

# # Query all hashrates from multiple runs
# df_nodes = pd.read_sql_query("""
#     SELECT run, hash_rate, creator_id
#     FROM simulation_results
#     WHERE experiment = 'Normal Run'
#     GROUP BY run, hash_rate, creator_id
# """, conn)

# # Count nodes per hashrate per run
# nodes_per_hashrate_run = df_nodes.groupby(['run','hash_rate']).count()['creator_id'].reset_index(name='node_count')

# # Average across runs
# avg_nodes_per_hashrate = nodes_per_hashrate_run.groupby('hash_rate')['node_count'].mean().reset_index()

# # Plot
# plt.figure(figsize=(10,6))
# plt.bar(avg_nodes_per_hashrate['hash_rate'], avg_nodes_per_hashrate['node_count'], color='skyblue', alpha=0.7)
# plt.xlabel("Node Hashrate")
# plt.ylabel("Average Number of Nodes")
# plt.title("Average Distribution of Node Hashrates Across Runs")
# plt.grid(True)
# plt.show()

# df = pd.read_sql_query("""
#     SELECT run, creator_id, hash_rate, block_id
#     FROM simulation_results
#     WHERE experiment = 'Normal Run'
# """, conn)

# # Count blocks per hashrate per run
# blocks_per_hashrate_run = df.groupby(['run','hash_rate']).count()['block_id'].reset_index(name='blocks_created')

# # Average blocks per hashrate across all runs
# avg_blocks_per_hashrate = blocks_per_hashrate_run.groupby('hash_rate')['blocks_created'].mean().reset_index()

# # Plot
# plt.figure(figsize=(10,6))
# plt.scatter(avg_blocks_per_hashrate['hash_rate'], avg_blocks_per_hashrate['blocks_created'], 
#             color='blue', s=80, alpha=0.7, label='Average Blocks')

# # Line of best fit
# slope, intercept = np.polyfit(avg_blocks_per_hashrate['hash_rate'], avg_blocks_per_hashrate['blocks_created'], 1)
# plt.plot(avg_blocks_per_hashrate['hash_rate'], slope*avg_blocks_per_hashrate['hash_rate'] + intercept,
#          color='red', linestyle='--', label='Trend Line')

# plt.xlabel("Node Hashrate")
# plt.ylabel("Average Blocks Produced")
# plt.title("Average Blocks Produced vs Node Hashrate Across Runs")
# plt.grid(True)
# plt.legend()
# plt.show()


# # Query number of forks per run for Equal Hash Rate
# df_forks_eq = pd.read_sql_query("""
#     SELECT run, MAX(number_of_forks) AS forks
#     FROM simulation_results
#     WHERE experiment = 'Equal Hash Rate'
#     GROUP BY run
#     ORDER BY run
# """, conn)

# print(df_forks_eq.head())

# plt.figure(figsize=(10,6))

# sns.barplot(x='run', y='forks', data=df_forks_eq, color='skyblue', alpha=0.7)
# plt.xlabel("Simulation Run")
# plt.ylabel("Number of Forks")
# plt.title("Number of Forks per Run — Equal Hash Rate Condition")
# plt.grid(True, linestyle='--', alpha=0.5)
# plt.show()
# avg_forks = df_forks_eq['forks'].mean()
# print(f"Average number of forks (Equal Hash Rate): {avg_forks:.2f}")

df_consensus_skw = pd.read_sql_query("""
    SELECT run, block_id, confirmation_time
    FROM simulation_results
    WHERE experiment = 'Normal2'
    ORDER BY run, block_id
""", conn)

print(df_consensus_skw.head())

# Remove blocks that never reached consensus
df_consensus_skw = df_consensus_skw[df_consensus_skw['confirmation_time'].notnull()]

avg_confirmation_per_run = df_consensus_skw.groupby('run')['confirmation_time'].mean().reset_index()
print(avg_confirmation_per_run)

plt.figure(figsize=(10,6))
sns.barplot(x='run', y='confirmation_time', data=avg_confirmation_per_run, color='skyblue', alpha=0.7)

plt.xlabel("Simulation Run")
plt.ylabel("Average Confirmation Time")
plt.title("Average Block Confirmation Time per Run — Skewed Hash Rate")
plt.grid(True, linestyle='--', alpha=0.5)
plt.show()


# Query number of forks per run for Equal Hash
df_forks_eq = pd.read_sql_query("""
    SELECT run, MAX(number_of_forks) AS forks
    FROM simulation_results
    WHERE experiment = 'Equal Hash'
    GROUP BY run
    ORDER BY run
""", conn)
df_forks_eq['experiment'] = 'Equal Hash'

# Query number of forks per run for Skewed Hash
df_forks_sk = pd.read_sql_query("""
    SELECT run, MAX(number_of_forks) AS forks
    FROM simulation_results
    WHERE experiment = 'Normal2'
    GROUP BY run
    ORDER BY run
""", conn)
df_forks_sk['experiment'] = 'Skewed Hash'

# Combine both datasets
df_forks_all = pd.concat([df_forks_eq, df_forks_sk], ignore_index=True)

# Plot forks per run for both experiments
plt.figure(figsize=(12,6))
sns.barplot(x='run', y='forks', hue='experiment', data=df_forks_all, alpha=0.7)
plt.xlabel("Simulation Run")
plt.ylabel("Number of Forks")
plt.title("Number of Forks per Run — Equal vs Skewed Hash Rate")
plt.grid(True, linestyle='--', alpha=0.5)
plt.legend(title="Experiment")
plt.show()

# Optional: print average forks
avg_forks_eq = df_forks_eq['forks'].mean()
avg_forks_sk = df_forks_sk['forks'].mean()
print(f"Average number of forks (Equal Hash): {avg_forks_eq:.2f}")
print(f"Average number of forks (Skewed Hash): {avg_forks_sk:.2f}")