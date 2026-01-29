#Imports:
import simpy
import random
from config import *

#Global variables:
env = simpy.Environment()
nodes = []
current_block_id = 0
current_node_id = 0

#Message class, defines structure of a message:
class Message:
    def __init__(self, sender_id, creation_time):
        #Set block ID:
        global current_block_id
        current_block_id += 1

        #Message attributes:
        self.block_id = current_block_id 
        self.size = block_size
        self.sender_id = sender_id
        self.creation_time = creation_time

#Node class, defines structure of a node:
class Node:
    def __init__(self, env):
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
            if block.block_id not in self.seen_blocks:
                #Marks block as seen, now that it has received it:
                self.seen_blocks.add(block.block_id)

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
    
    def send_single_node(self, block, neighbour):
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
        block = Message(self.node_id, self.env.now)
        self.seen_blocks.add(block.block_id)

        log_message = self.env.now, "Created block: " + str(block.block_id)
        self.log.append(log_message)

        self.metrics[block.block_id] = self.env.now

        self.env.process(self.send_block(block))

        return block


def instantiate_nodes():
    for i in range(number_of_nodes):
        new_node = Node(env)
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

    
instantiate_nodes()
create_topology()

block_proposer = random.choice(nodes)
block = block_proposer.create_block()

env.run(until=100)

for node in nodes:
    print(f"Node {node.node_id} log:")
    for entry in node.log:
        print(entry)
    print()

consensus_time = calculate_consenus_time(block)

if consensus_time == None:
    print("CONSENSUS WAS NOT MET BEFORE DEADLINE.")
elif consensus_time > consensus_deadline:
    print("CONSENSUS MET BUT DEADLINE EXCEEDED BY: " + str(consensus_time - consensus_deadline))
elif consensus_time == consensus_deadline:
    print("CONSENSUS DEADLINE MET.")
else:
    print("CONSENSUS ACHIEVED BEFORE DEADLINE, TIME REMAINING BEFORE DEADLINE: " + str(consensus_deadline - consensus_time))
