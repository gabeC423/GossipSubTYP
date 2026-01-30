#Imports:
import simpy
import random
from config import *

#Global variables:
env = simpy.Environment()
nodes = []
current_block_id = 0
current_node_id = 0
proposer_nodes = []
created_blocks = []

#Message class, defines structure of a message:
class Message:
    def __init__(self, block_id, sender_id, creation_time, height, parent = None):
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

#Node class, defines structure of a node:
class Node:
    def __init__(self, env, initial_end_chain):
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
            log_message = self.env.now, "Added new neighbour: " + str(neighbour.node_id)
            self.log.append(log_message)
        else:
            #If the peer degree condition is not met then the node locally logs the event as unsuccessful.
            log_message = self.env.now, "Neighbour list has hit peer degree, could not add node: " + str(neighbour.node_id)
            self.log.append(log_message)

    #Run method:
    def run(self):
        while True:
            block = yield self.inbox.get()
            #Calculate recieve delay:
            receive_delay = block.size / self.bandwidth
            yield self.env.timeout(receive_delay)

            #Checks that the node has not already received this block:
            if block.block_id not in self.seen_blocks and (block.parent is None or block.parent in self.blocks.values()):
                #Marks block as seen, now that it has received it:
                self.seen_blocks.add(block.block_id)
                self.blocks[block.block_id] = block

                #Checks if the block's parent exists and is an end of a chain:
                if block.parent is not None and block.parent in self.chain_ends:
                    #If so it is removed so that it can be replaced by it's child:
                    self.chain_ends.remove(block.parent)
                
                #Set current block as new chain end:
                self.chain_ends.add(block)

                #Locally logs this event as successful:
                log_message = self.env.now, "Received block: " + str(block.block_id)
                self.log.append(log_message)
                
                #Locally Records the time the node received the block:
                self.metrics[block.block_id] = self.env.now
                
                self.env.process(self.send_block(block))
            else:
                #If block has already been received, node locally logs this event as unsucessful:
                log_message = self.env.now, "Block has already been received by this node: " + str(block.block_id)
                self.log.append(log_message)
    
    #Helper method for sendning to a single node:
    def send_single_node(self, block, neighbour):
        #Calculates send delay:
        send_delay = block.size / self.bandwidth

        yield neighbour.env.timeout(send_delay)
        yield neighbour.inbox.put(block)
    
    #Method for sending blocks:
    #Chat GPT helped with this function.
    def send_block(self, block):
        active_nodes = []
        queue = list(self.neighbours)

        while queue or active_nodes:
            while len(active_nodes) < max_parallel_nodes and queue:
                neighbour = queue.pop(0)
                process = self.env.process(self.send_single_node(block, neighbour))
                active_nodes.append(process)

            if active_nodes:
                yield simpy.events.AnyOf(self.env, active_nodes)

            active_nodes = [p for p in active_nodes if not p.triggered]

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
        block = Message(current_block_id, self.node_id, self.env.now, current_best_end.height + 1, current_best_end)

        self.end_of_chain_block = block
        self.seen_blocks.add(block.block_id)
        self.blocks[block.block_id] = block
        self.chain_ends.remove(current_best_end)
        self.chain_ends.add(block)

        log_message = self.env.now, "Created block: " + str(block.block_id)
        self.log.append(log_message)

        self.metrics[block.block_id] = self.env.now
        self.env.process(self.send_block(block))

        return block

def instantiate_nodes():
    for i in range(number_of_nodes):
        new_node = Node(env, start_block)
        nodes.append(new_node)

def create_topology():
    for node in nodes:
        while len(node.neighbours) < peer_degree:
            proposed_peer = nodes[random.randint(0, number_of_nodes - 1)]

            while proposed_peer in node.neighbours or proposed_peer == node:
                proposed_peer = nodes[random.randint(0, number_of_nodes - 1)]

            node.add_neighbour(proposed_peer)
            log_message = node.env.now, "Added neighbour: " + str(proposed_peer.node_id)
            node.log.append(log_message) 

def calculate_consenus_time(block):
    highest_time = None
    block_received_by_all = True
    consensus_time = None

    for node in nodes:
        if block.block_id in node.metrics:
            if highest_time is None or node.metrics[block.block_id] > highest_time:
                highest_time = node.metrics[block.block_id]
        else:
            block_received_by_all = False

    if block_received_by_all == True:
        consensus_time = highest_time - block.creation_time
    else:
        consensus_time = None
    
    return consensus_time

#Main section of code:
start_block = Message(current_block_id, sender_id = None, creation_time = 0, height = 0, parent = None)
instantiate_nodes()
create_topology()

for node in nodes:
    if random.random() < proposer_probability:
        proposer_nodes.append(node)

for node in proposer_nodes:
    created_blocks.append(node.create_block())


env.run(until = simulation_time)

for node in nodes:
    print(f"Node {node.node_id} log:")
    for entry in node.log:
        print(entry)
    print()

for block in created_blocks:
    consensus_time = calculate_consenus_time(block)

    if consensus_time == None:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS WAS NOT MET BEFORE DEADLINE.")
    elif consensus_time > consensus_deadline:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS MET BUT DEADLINE EXCEEDED BY: " + str(consensus_time - consensus_deadline))
    elif consensus_time == consensus_deadline:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS DEADLINE MET.")
    else:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS ACHIEVED BEFORE DEADLINE, TIME REMAINING BEFORE DEADLINE: " + str(consensus_deadline - consensus_time))
