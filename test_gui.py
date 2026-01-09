import tkinter as tk
from tkinter import messagebox

root = tk.Tk()
root.title("测试窗口")
root.geometry("300x200")

label = tk.Label(root, text="如果你能看到这个窗口，说明GUI正常工作！", wraplength=250)
label.pack(pady=50)

btn = tk.Button(root, text="点击关闭", command=root.destroy)
btn.pack()

root.mainloop()
print("窗口已关闭")
