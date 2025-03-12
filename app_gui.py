import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext, ttk
import threading
import time
import psutil
import requests
import json

class ChatGUI(tk.Frame):

    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("AI测试助手")
        self.grid(sticky=tk.NSEW)
        self.create_widgets()
        self.load_config()
        self.is_new_response = False
        self.total_requests = 0
        self.concurrent_requests = 0
        
        # 添加菜单栏
        self.menu_bar = tk.Menu(self.master)
        self.master.config(menu=self.menu_bar)
        self.settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.settings_menu.add_command(label="设置", command=self.open_settings)
        self.menu_bar.add_cascade(label="选项", menu=self.settings_menu)

        # 配置网格布局权重
        self.master.rowconfigure(0, weight=1)
        self.master.rowconfigure(2, weight=0)
        self.master.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def create_widgets(self):
        # 聊天历史区域
        self.history = scrolledtext.ScrolledText(self, wrap=tk.WORD, state='disabled')
        self.history.grid(row=0, column=0, columnspan=2, sticky='nsew')

        # 输入区域
        self.input_frame = ttk.Frame(self)
        self.input_frame.grid(row=1, column=0, columnspan=2, sticky='nsew')

        # 状态栏
        self.status_bar = ttk.Label(self, relief='sunken', anchor=tk.W)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky='ew')
        
        self.input = tk.Text(self.input_frame, height=4)
        self.input.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        
        # 按钮容器
        self.btn_frame = ttk.Frame(self.input_frame)
        self.btn_frame.grid(row=0, column=1, sticky='ns')
        
        self.send_btn = ttk.Button(self.btn_frame, text="发送", command=self.on_send)
        self.send_btn.pack(side=tk.TOP, pady=2)
        
        self.clear_btn = ttk.Button(self.btn_frame, text="清除", command=self.clear_history)
        self.clear_btn.pack(side=tk.TOP, pady=2)
        
        # 配置输入区域权重
        self.input_frame.columnconfigure(0, weight=1)
        self.input_frame.rowconfigure(0, weight=1)

    def load_config(self):
        try:
            with open('config.json', encoding='utf-8') as f:
                self.config = json.load(f)
                self.config['temperature'] = float(self.config.get('temperature', 0.7))
                self.config['max_tokens'] = int(self.config.get('max_tokens', 80000))
                if 'seed' in self.config and self.config['seed'] is not None:
                    self.config['seed'] = int(self.config['seed'])
        except Exception as e:
            print(f'配置加载错误: {str(e)}')

    def on_send(self):
        prompt = self.input.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showerror("错误", "输入内容不能为空")
            return
        self.input.delete('1.0', tk.END)
        self.append_history("用户", prompt)
        self.is_new_response = True

        threading.Thread(
            target=self.get_ai_response,
            args=(prompt,),
            daemon=True
        ).start()

    def append_history(self, role, content):
        self.history.configure(state='normal')
        self.history.insert(tk.END, f"\n{role}:\n{content}\n\n")
        self.history.see(tk.END)
        self.history.configure(state='disabled')

    def get_ai_response(self, prompt):
        self.total_requests += 1
        self.concurrent_requests += 1
        
        # 获取初始系统资源
        initial_cpu = psutil.cpu_percent()
        initial_mem = psutil.virtual_memory().percent
        try:
            response = requests.post(
                url=f"{self.config['api_base']}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config['api_key']}"
                },
                json={
                    "model": self.config['model_name'],
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True
                },
                stream=True
            )
            response.raise_for_status()
            
            buffer = b''
            full_response = ''
            start_time = time.time()
            first_token_time = None
            last_token_time = None
            token_count = 0
            for chunk in response.iter_content(1024):
                if chunk:
                    buffer += chunk
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line.startswith(b'data: '):
                            json_str = line[6:]
                            if json_str.strip() == b'[DONE]':
                                break
                            try:
                                data = json.loads(json_str)
                                content = data['choices'][0]['delta'].get('content', '')
                                full_response += content
                                current_time = time.time()
                                
                                if not first_token_time:
                                    first_token_time = current_time
                                else:
                                    last_token_time = current_time
                                
                                token_count += len(content.split())
                                self.history.after(0, self.update_stream, content)
                                self.history.after(0, self.history.see, tk.END)
                                # 流式处理结束后更新统计
                                if token_count > 0:
                                    total_time = time.time() - start_time
                                    first_delay = (first_token_time - start_time) * 1000 if first_token_time else 0
                                    non_first_delay = (last_token_time - first_token_time) * 1000 if last_token_time and first_token_time else 0
                                    non_first_tokens = max(token_count - 1, 0)
                                    
                                    avg_non_first_delay = non_first_delay / non_first_tokens if non_first_tokens > 0 else 0
                                    stats = (
                                        f"首token: {first_delay:.1f}ms | "
                                        f"平均非首: {avg_non_first_delay:.1f}ms | "
                                        f"吞吐: {token_count / total_time:.1f}t/s | "
                                        f"长度: {len(full_response)}"
                                    )
                                    self.history.after(0, lambda: self.status_bar.config(text=stats))
                            except Exception as e:
                                self.history.after(0, self.append_history, "系统", f"数据解析错误: {str(e)}")
        
        except Exception as e:
            if token_count > 0:
                total_time = time.time() - start_time
                first_delay = (first_token_time - start_time) * 1000 if first_token_time else 0
                non_first_delay = (last_token_time - first_token_time) * 1000 if last_token_time and first_token_time else 0
                non_first_tokens = max(token_count - 1, 0)
                
                stats = (
                    f"输入长度\t{len(prompt)}\n"
                    f"输出长度\t{len(full_response)}\n"
                    f"总时长(s)\t{total_time:.2f}\n"
                    f"首token延迟(ms)\t{first_delay:.1f}\n"
                    f"非首token延迟(ms)\t{non_first_delay / non_first_tokens if non_first_tokens >0 else 0:.1f}\n"
                    f"非首token吞吐(Tokens/s)\t{non_first_tokens / (non_first_delay / 1000) if non_first_delay >0 else 0:.1f}\n"
                    f"吞吐(Tokens/s)\t{token_count / total_time:.1f}"
                )
                self.history.after(0, lambda: self.status_bar.config(text=f"首token: {first_delay:.1f}ms | 吞吐: {token_count / total_time:.1f}t/s | 长度: {len(full_response)}字符"))
            
            # 异常时也更新统计信息
            if token_count > 0:
                total_time = time.time() - start_time
                first_delay = (first_token_time - start_time) * 1000 if first_token_time else 0
                avg_non_first_delay = non_first_delay / non_first_tokens if non_first_tokens > 0 else 0
                stats = (
                    f"首token: {first_delay:.1f}ms | "
                    f"平均非首: {avg_non_first_delay:.1f}ms | "
                    f"接收tokens: {token_count} | "
                    f"错误: {str(e)}"
                )
                self.history.after(0, lambda: self.status_bar.config(text=stats))
            self.history.after(0, self.append_history, "系统", f"API错误: {str(e)}")

    def clear_history(self):
        self.history.configure(state='normal')
        self.history.delete(1.0, tk.END)
        self.history.configure(state='disabled')
        self.is_new_response = False
        self.total_requests = 0
        self.concurrent_requests = 0

    def update_stream(self, content):
        self.history.configure(state='normal')
        if self.is_new_response:
            self.history.insert(tk.END, "\nAI：")
            self.is_new_response = False
        self.total_requests = 0
        self.concurrent_requests = 0
        self.history.insert(tk.END, content)
        self.history.see(tk.END)
        self.history.configure(state='disabled')

    def open_settings(self):
        SettingsWindow(self)

class SettingsWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.title("系统设置")
        self.geometry("500x400")
        self.create_widgets()
        self.load_current_values()

    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 创建滚动区域
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 配置项输入框
        entries_frame = ttk.Frame(scrollable_frame)
        entries_frame.pack(fill=tk.X, padx=10, pady=10)

        self.entries = {}
        fields = [
            ("API密钥:", "api_key"),
            ("API地址:", "api_base"),
            ("模型名称:", "model_name"),
            ("系统提示词:", "system_prompt"),  # 新增系统提示词字段
            ("温度值 (0-2):", "temperature"),
            ("最大token数:", "max_tokens"),
            ("停止符 (逗号分隔):", "stop"),
            ("Top P值:", "top_p"),
            ("随机种子:", "seed")
        ]

        for i, (label_text, field) in enumerate(fields):
            frame = ttk.Frame(entries_frame)
            frame.grid(row=i, column=0, sticky=tk.EW, pady=2)
            
            label = ttk.Label(frame, text=label_text, width=15)
            label.pack(side=tk.LEFT)
            
            entry = ttk.Entry(frame)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.entries[field] = entry

        # 保存按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="保存", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.LEFT)

    def load_current_values(self):
        for field, entry in self.entries.items():
            value = self.master.config.get(field, "")
            if isinstance(value, list):
                entry.insert(0, ",".join(value))
            elif value is None:
                entry.insert(0, "")
            else:
                entry.insert(0, str(value))

    def save_settings(self):
        new_config = {}
        try:
            # 处理特殊字段
            new_config["api_key"] = self.entries["api_key"].get()
            new_config["api_base"] = self.entries["api_base"].get()
            new_config["model_name"] = self.entries["model_name"].get()
            
            # 数值类型处理
            new_config["temperature"] = float(self.entries["temperature"].get())
            new_config["max_tokens"] = int(self.entries["max_tokens"].get())
            
            # 处理停止符列表
            stop_str = self.entries["stop"].get()
            new_config["stop"] = [s.strip() for s in stop_str.split(",")] if stop_str else []
            
            # 处理可选参数
            new_config["top_p"] = float(self.entries["top_p"].get() or 1)
            
            seed_str = self.entries["seed"].get()
            new_config["seed"] = int(seed_str) if seed_str.strip() else None
            
            # 处理系统提示词
            system_prompt = self.entries["system_prompt"].get()
            new_config["system_prompt"] = system_prompt if system_prompt.strip() else None
            
            # 保存到文件
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=2, ensure_ascii=False)
            
            # 更新主界面配置
            self.master.config = new_config
            self.destroy()
            
        except ValueError as e:
            tk.messagebox.showerror("输入错误", f"无效的数值类型: {str(e)}")
        except Exception as e:
            tk.messagebox.showerror("保存错误", f"保存配置失败: {str(e)}")

    def monitor_system_resources(self):
        while True:
            self.cpu_usage = psutil.cpu_percent(interval=1)
            self.mem_usage = psutil.virtual_memory().percent
            time.sleep(5)

    def __del__(self):
        self.concurrent_requests -= 1

if __name__ == '__main__':
    root = tk.Tk()
    root.geometry("800x600")
    app = ChatGUI(root)
    root.mainloop()