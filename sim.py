# Philosophers' Restaurant: the full simulator. Built by Henock, one milestone at a time.
#
# RULE OF THE HOUSE: worker threads NEVER touch tkinter. They only send messages:
#   send("state", i, "thinking" | "hungry" | "eating")  -> philosopher i changed state
#   send("fork", f, i)      -> fork f is now held by philosopher i
#   send("fork", f, None)   -> fork f is back on the table
import math
import queue
import random
import sys
import threading
import time
import tkinter as tk



NAMES = ["Plato", "Kant", "Hume", "Socrates", "Confucius"]
N = len(NAMES)
COLORS = {"thinking": "#9aa5b1", "hungry": "#f0a030", "eating": "#3cb371"}
events = queue.Queue()


def send(*message):
    events.put(message)


# ======================================================================================================================================


forks = [threading.Lock() for _ in range(N)]
MODE = "naive"  # "naive" | "waiter" | "ordering"
for arg in sys.argv:
    if arg in ("naive", "waiter", "ordering","manager"):
         MODE = arg
waiter = threading.Semaphore(N - 1)  # the waiter: 4 seat permits for 5 philosophers
state_lock = threading.Lock()  
holding = {i: [] for i in range(N)}               # i -> list of forks i holds
waiting_for = {i: None for i in range(N)}         # i -> fork i is waiting for, or None
put_down = [threading.Event() for _ in range(N)]  # manager raises put_down[i] to preempt i
rollbacks = [0] * N
SLOTS = 3
counter = []
counter_lock = threading.Lock()  # protects counter and SLOTS
dish_ready = threading.Semaphore(0)
free_slots = threading.Semaphore(SLOTS)
board = {"total_meals": 0, **{name: 0 for name in NAMES}}

rw_lock = threading.Semaphore(1)  # held by ONE writer, or by the reader GROUP
count_lock = threading.Lock()     # protects read_count
read_count = 0 

                 # how many readers are inside right now

  

def record_meal(i):
    rw_lock.acquire()          # writers need the board all to themselves
    board[NAMES[i]] += 1               # step 1 of the update
    time.sleep(0.05)
    board["total_meals"] += 1
    rw_lock.release()

def start_reading():
    global read_count
    with count_lock:
        read_count +=1
        if read_count ==1:
            rw_lock.acquire()
def stop_reading():
    global read_count 
    with count_lock:
        read_count -= 1
        if read_count == 0:
            rw_lock.release()

def inspector(k):
    while True:
        time.sleep(0.5)
        start_reading()
        per = sum(board[name] for name in NAMES )
        total = board["total_meals"]
        stop_reading()
        send("board", f"Inspector {k}: total={total}, sum={per} " + ("OK" if per == total else "TORN READ!"))




def take_fork(i, f):
    with state_lock:
     waiting_for[i] = f
    while True:
        if forks[f].acquire(timeout=0.1):  # try to take the fork, but not forever
            break 
        if put_down[i].is_set():  # manager preempted i while it was waiting for f
            with state_lock:
                waiting_for[i] = None
            return False
    with state_lock:
     waiting_for[i] = None
     holding[i].append(f)
    send("fork", f, i)
    return True

def drop_all(i):
    with state_lock:
        for f in holding[i]:
            send("fork", f, None)
            forks[f].release()
            
        holding[i].clear()

def rollback(i):
    drop_all(i)
    if MODE == "waiter":
        waiter.release()  # leave the table: a seat opens up


def build_wait_for(holding, waiting_for):
    """holding: name -> list of forks held. waiting_for: name -> fork wanted (or None).
    Returns name -> name of the philosopher they're waiting on (or None)."""
    fork_holder = {}
    for name, forks in holding.items():
        for fork in forks:
            fork_holder[fork] = name
    return {name: fork_holder.get(fork) if fork is not None else None
            for name, fork in waiting_for.items()}

def find_cycle(waits_on):
    """Follow the arrows from each philosopher. Coming back to someone already
    on this path means a loop; reaching None means the chain has an end."""
    for start in waits_on:
        path = []
        current = start
        while current is not None and current not in path:
            path.append(current)
            current = waits_on[current]
        if current is not None:              # we came back around to someone on the path
            return path[path.index(current):]  # just the loop part
    return None

def manager():
    sleep_time = 0.5
    while True:
        time.sleep(sleep_time)
        with state_lock:
            if cycle := find_cycle(build_wait_for(holding, waiting_for)):
                victim =min(cycle, key=lambda i: rollbacks[i])  # pick the philosopher with the fewest rollbacks
                rollbacks[victim] += 1
                put_down[victim].set()  # preempt the victim
                send("victim", victim)
                send ("manager", f"Deadlock detected! Preempting {NAMES[victim]} (rollbacks: {rollbacks})")

def chef():
    while True:
        time.sleep(random.uniform(0.5, 1.5))  # time to cook a dish
        free_slots.acquire()
        with counter_lock:
            counter.append("dish")
            send("counter", len(counter), SLOTS)
        dish_ready.release()  # signal that a dish is ready
            
                 


def philosopher(i):
    
    
    left=i
    right=(i+1)%N

    if MODE == "ordering":
        first, second = min(left, right), max(left, right)  # Confucius: f0 before f4
    else:
        first, second = left, right
    has_dish = False
    while True:
        send("state", i, "thinking")
        time.sleep(random.uniform(0.2, 1.0))
        send("state", i, "hungry")
        if not has_dish:
            dish_ready.acquire()  # wait for a dish to be ready
            with counter_lock:
                counter.pop(0)
                send("counter", len(counter), SLOTS)
            free_slots.release()  # signal that a slot is now free
            has_dish = True
        put_down[i].clear()  # reset the preemption flag for this meal
        if MODE == "waiter":
            waiter.acquire()              # wait outside if 4 are already seated
        if not take_fork(i, first):
            rollback(i) 
            continue
        time.sleep(0.2)
        if not take_fork(i, second):
            rollback(i)
            continue
        send("state", i, "eating")
        record_meal(i)
        time.sleep(0.3)
        drop_all(i)
        has_dish = False
        if MODE == "waiter":
            waiter.release()              # leave the table: a seat opens up
      


# ============================================================================
# GUI: provided. Runs only on the main thread. (Read it, but no need to edit.)
# ============================================================================

root = tk.Tk()
root.title(f"Philosophers' Restaurant ({MODE})")
canvas = tk.Canvas(root, width=460, height=460, bg="white")
canvas.pack()
status = tk.Label(root, text="", font=("Segoe UI", 10), fg="#b03030", wraplength=440, height=3)
status.pack()
kitchen = tk.Label(root, text="", font=("Consolas", 11))
kitchen.pack()
board_label = tk.Label(root, text="", font=("Consolas", 10), justify="left")
board_label.pack(pady=(0, 8))
CX, CY = 230, 230


def point(angle, radius):
    return CX + radius * math.cos(angle), CY + radius * math.sin(angle)


def seat_angle(i):
    return 2 * math.pi * i / N - math.pi / 2


canvas.create_oval(CX - 110, CY - 110, CX + 110, CY + 110, fill="#f5e6c8", outline="")  # table

seats, seat_xy = [], []
for i, name in enumerate(NAMES):
    x, y = point(seat_angle(i), 165)
    seats.append(canvas.create_oval(x - 36, y - 36, x + 36, y + 36, fill=COLORS["thinking"], outline=""))
    canvas.create_text(x, y, text=name, font=("Segoe UI", 9, "bold"))
    seat_xy.append((x, y))

# Fork f sits between philosopher f (its left owner) and philosopher f - 1.
fork_home, fork_dot, fork_line = [], [], []
for f in range(N):
    x, y = point(seat_angle(f) - math.pi / N, 85)
    fork_home.append((x, y))
    fork_line.append(canvas.create_line(x, y, x, y, width=3, fill="#555"))
    fork_dot.append(canvas.create_oval(x - 10, y - 10, x + 10, y + 10, fill="white", outline="#555", width=2))
    canvas.create_text(x, y, text=f"f{f}", font=("Segoe UI", 8))


def unflash(i):
    canvas.itemconfig(seats[i], outline="", width=1)


def poll_events():
    try:
        while True:
            message = events.get_nowait()
            kind = message[0]
            if kind == "state":
                _, i, state = message
                canvas.itemconfig(seats[i], fill=COLORS[state])
            elif kind == "fork":
                _, f, holder = message
                x, y = fork_home[f]
                if holder is None:  # back on the table
                    canvas.coords(fork_line[f], x, y, x, y)
                    canvas.itemconfig(fork_dot[f], fill="white")
                else:               # draw a line from the fork to whoever holds it
                    hx, hy = seat_xy[holder]
                    canvas.coords(fork_line[f], x, y, hx, hy)
                    canvas.itemconfig(fork_dot[f], fill="#ffd966")
            elif kind == "manager":   # send("manager", "some text") -> shown under the table
                _, text = message
                status.config(text=text)
            elif kind == "victim":    # send("victim", i) -> red ring around philosopher i for 1 s
                _, i = message
                canvas.itemconfig(seats[i], outline="#d62828", width=5)
                root.after(1000, unflash, i)
            elif kind == "counter":   # send("counter", dishes_on_counter, slots) -> kitchen line
                _, dishes, slots = message
                kitchen.config(text="Kitchen counter: [" + "#" * dishes + "." * (slots - dishes) + "]")
            elif kind == "board":     # send("board", "inspector report text") -> bottom line
                _, text = message
                board_label.config(text=text)
    except queue.Empty:
        pass
    finally:
        root.after(30, poll_events)  # ALWAYS schedule the next check, even after an error


for i in range(N):
    threading.Thread(target=philosopher, args=(i,), daemon=True).start()
if MODE == "manager" and "manager" in globals():  # starts once you've written manager()
    threading.Thread(target=manager, daemon=True).start()
if "chef" in globals():                              # starts once you've written chef()
    threading.Thread(target=chef, daemon=True).start()
if "inspector" in globals():                         # starts 3 once you've written inspector(k)
    for k in range(3):
        threading.Thread(target=inspector, args=(k,), daemon=True).start()

poll_events()
if "--demo" in sys.argv:
    root.after(3000, root.destroy)
root.mainloop()
