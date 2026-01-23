import simpy
from config import *

env = simpy.Environment()

current_block_id = 0
current_node_id = 0

class Message:
    def __init__(self, sender_id):
        global current_block_id
        current_block_id += 1

        self.block_id = current_block_id 
        self.size = block_size
        self.sender_id = sender_id

class Node:
    def __init__(self, env):
        global current_node_id
        current_node_id += 1

        self.bandwidth = 30
        self.neighbours = []
        self.node_id = current_node_id
        self.inbox = simpy.Store(env)
        self.seen_blocks = set()
        self.log = []

        env.process(self.run())

    def add_neighbour(self, neighbour):
        global peer_degree

        if len(self.neighbours) < peer_degree:
            self.neighbours.append(neighbour)
            log_message = "Added new neighbour: " + str(neighbour.node_id)
            self.log.append(log_message)
        else:
            log_message = "Neighbour list has hit peer degree, could not add node: " + str(neighbour.node_id)
            self.log.append(log_message)

    def receive_block(self, block):
        if block.block_id not in self.seen_blocks:
            self.seen_blocks.add(block.block_id)
            log_message = "Block added to seen blocks: " + str(block.block_id)
            self.log.append(log_message)
        else:
            log_message = "Block has already been received by this node: " + str(block.block_id)
            self.log.append(log_message)
    
    def send_block(self, block):
        for neighbour in self.neighbours:
            send_delay = block.size / self.bandwidth
            yield env.timeout(send_delay)
            yield neighbour.inbox.put(block)

