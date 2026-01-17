/**
 * 聊天区域逻辑
 */
import { chat, state as stateApi } from './api.js';

class Chat {
    constructor() {
        this.container = document.getElementById('chat-messages');
        this.input = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('send-btn');
        this.conversationId = null;
        this.isStreaming = false;
        this.messages = [];
    }
    
    /**
     * 初始化聊天区域
     */
    init() {
        this.bindEvents();
        this.showWelcome();
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 发送按钮
        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.send());
        }
        
        // 输入框
        if (this.input) {
            this.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.send();
                }
            });
            
            // 自动调整高度
            this.input.addEventListener('input', () => {
                this.input.style.height = 'auto';
                this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px';
            });
        }
        
        // 重新生成按钮
        const regenBtn = document.getElementById('regenerate-btn');
        if (regenBtn) {
            regenBtn.addEventListener('click', () => this.regenerate());
        }
    }
    
    /**
     * 设置当前会话
     */
    async setConversation(conv) {
        if (!conv) {
            this.conversationId = null;
            this.messages = [];
            this.showWelcome();
            return;
        }
        
        this.conversationId = conv.id;
        await this.loadMessages();
        
        // 更新标题
        const titleEl = document.getElementById('chat-title');
        if (titleEl) {
            titleEl.textContent = conv.title;
        }
    }
    
    /**
     * 加载消息历史
     */
    async loadMessages() {
        if (!this.conversationId) return;
        
        try {
            this.messages = await chat.getMessages(this.conversationId);
            this.render();
            this.scrollToBottom();
        } catch (error) {
            console.error('加载消息失败:', error);
            this.showError('加载消息失败');
        }
    }
    
    /**
     * 渲染消息列表
     */
    render() {
        if (!this.container) return;
        
        if (this.messages.length === 0) {
            this.showWelcome();
            return;
        }
        
        this.container.innerHTML = this.messages.map((msg, index) => 
            this.renderMessage(msg, index)
        ).join('');
        
        // 绑定消息操作按钮
        this.bindMessageActions();
    }
    
    /**
     * 渲染单条消息
     */
    renderMessage(msg, index) {
        const isUser = msg.role === 'user';
        const avatar = isUser ? '👤' : '🤖';
        
        return `
            <div class="message ${msg.role}" data-index="${index}">
                <div class="message-avatar">${avatar}</div>
                <div class="message-content">
                    <div class="message-bubble">
                        <div class="message-text">${this.escapeHtml(msg.content)}</div>
                    </div>
                    <div class="message-meta">
                        <div class="message-actions">
                            <button class="message-action-btn" data-action="edit" data-tooltip="编辑">✏️</button>
                            <button class="message-action-btn danger" data-action="delete" data-tooltip="删除">🗑️</button>
                            ${!isUser ? `<button class="message-action-btn" data-action="regen" data-tooltip="重新生成">🔄</button>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * 绑定消息操作按钮事件
     */
    bindMessageActions() {
        this.container.querySelectorAll('.message-action-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = btn.dataset.action;
                const messageEl = btn.closest('.message');
                const index = parseInt(messageEl.dataset.index);
                
                switch (action) {
                    case 'edit':
                        this.editMessage(index);
                        break;
                    case 'delete':
                        this.deleteMessage(index);
                        break;
                    case 'regen':
                        this.regenerate();
                        break;
                }
            });
        });
    }
    
    /**
     * 发送消息
     */
    async send() {
        if (!this.conversationId || this.isStreaming) return;
        
        const content = this.input.value.trim();
        if (!content) return;
        
        this.input.value = '';
        this.input.style.height = 'auto';
        
        // 添加用户消息到 UI
        this.messages.push({ role: 'user', content });
        this.render();
        this.scrollToBottom();
        
        // 添加 AI 消息占位
        const aiMessageIndex = this.messages.length;
        this.messages.push({ role: 'assistant', content: '' });
        this.render();
        
        // 获取 AI 消息元素
        const aiMessageEl = this.container.querySelector(`[data-index="${aiMessageIndex}"] .message-text`);
        
        this.isStreaming = true;
        this.updateSendButton(true);
        
        // 发送请求（流式）
        chat.sendMessage(this.conversationId, content, {
            onChunk: (chunk) => {
                this.messages[aiMessageIndex].content += chunk;
                if (aiMessageEl) {
                    aiMessageEl.innerHTML = this.escapeHtml(this.messages[aiMessageIndex].content) + 
                        '<span class="streaming-cursor"></span>';
                }
                this.scrollToBottom();
            },
            onDone: (data) => {
                this.messages[aiMessageIndex].content = data.output;
                this.isStreaming = false;
                this.updateSendButton(false);
                this.render();
                this.scrollToBottom();
                
                // 更新状态面板
                this.updateStatePanel(data);
            },
            onError: (error) => {
                console.error('发送失败:', error);
                this.messages.pop(); // 移除空的 AI 消息
                this.isStreaming = false;
                this.updateSendButton(false);
                this.render();
                this.showToast('发送失败: ' + error.message, 'error');
            },
        });
    }
    
    /**
     * 重新生成最后回复
     */
    async regenerate() {
        if (!this.conversationId || this.isStreaming) return;
        
        // 找到最后一条 AI 消息
        let lastAiIndex = -1;
        for (let i = this.messages.length - 1; i >= 0; i--) {
            if (this.messages[i].role === 'assistant') {
                lastAiIndex = i;
                break;
            }
        }
        
        if (lastAiIndex < 0) {
            this.showToast('没有可重新生成的消息', 'error');
            return;
        }
        
        // 清空当前 AI 消息
        this.messages[lastAiIndex].content = '';
        this.render();
        
        const aiMessageEl = this.container.querySelector(`[data-index="${lastAiIndex}"] .message-text`);
        
        this.isStreaming = true;
        this.updateSendButton(true);
        
        chat.regenerate(this.conversationId, {
            onChunk: (chunk) => {
                this.messages[lastAiIndex].content += chunk;
                if (aiMessageEl) {
                    aiMessageEl.innerHTML = this.escapeHtml(this.messages[lastAiIndex].content) + 
                        '<span class="streaming-cursor"></span>';
                }
                this.scrollToBottom();
            },
            onDone: (data) => {
                this.messages[lastAiIndex].content = data.output;
                this.isStreaming = false;
                this.updateSendButton(false);
                this.render();
                this.updateStatePanel(data);
            },
            onError: (error) => {
                console.error('重新生成失败:', error);
                this.isStreaming = false;
                this.updateSendButton(false);
                this.loadMessages(); // 重新加载
                this.showToast('重新生成失败: ' + error.message, 'error');
            },
        });
    }
    
    /**
     * 编辑消息
     */
    async editMessage(index) {
        const msg = this.messages[index];
        const newContent = prompt('编辑消息:', msg.content);
        
        if (newContent === null || newContent === msg.content) return;
        
        try {
            await chat.editMessage(this.conversationId, index, newContent);
            this.messages[index].content = newContent;
            this.render();
            this.showToast('消息已更新', 'success');
        } catch (error) {
            console.error('编辑失败:', error);
            this.showToast('编辑失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 删除消息
     */
    async deleteMessage(index) {
        if (!confirm('确定删除这条消息吗？')) return;
        
        try {
            await chat.deleteMessage(this.conversationId, index);
            await this.loadMessages();
            this.showToast('消息已删除', 'success');
        } catch (error) {
            console.error('删除失败:', error);
            this.showToast('删除失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 更新状态面板
     */
    updateStatePanel(data) {
        // 更新情绪显示
        const moodEl = document.getElementById('current-mood');
        if (moodEl && data.mood) {
            moodEl.textContent = data.mood;
        }
        
        // 更新内心想法
        const thoughtEl = document.getElementById('inner-thought');
        if (thoughtEl && data.thought) {
            thoughtEl.textContent = data.thought;
        }
    }
    
    /**
     * 更新发送按钮状态
     */
    updateSendButton(loading) {
        if (this.sendBtn) {
            this.sendBtn.disabled = loading;
            this.sendBtn.innerHTML = loading ? 
                '<span class="spinner"></span>' : 
                '发送';
        }
    }
    
    /**
     * 显示欢迎消息
     */
    showWelcome() {
        if (!this.container) return;
        
        this.container.innerHTML = `
            <div class="welcome-message">
                <h2>👋 欢迎使用 AgentTest</h2>
                <p>选择或创建一个会话开始聊天</p>
                <div class="quick-prompts">
                    <button class="quick-prompt" data-prompt="你好！">你好！</button>
                    <button class="quick-prompt" data-prompt="介绍一下你自己">介绍一下你自己</button>
                    <button class="quick-prompt" data-prompt="今天心情怎么样？">今天心情怎么样？</button>
                </div>
            </div>
        `;
        
        // 绑定快捷提示点击
        this.container.querySelectorAll('.quick-prompt').forEach(btn => {
            btn.addEventListener('click', () => {
                if (this.input && this.conversationId) {
                    this.input.value = btn.dataset.prompt;
                    this.send();
                }
            });
        });
    }
    
    /**
     * 显示错误
     */
    showError(message) {
        if (this.container) {
            this.container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text" style="color: var(--accent-pink)">
                        ${this.escapeHtml(message)}
                    </div>
                </div>
            `;
        }
    }
    
    /**
     * 滚动到底部
     */
    scrollToBottom() {
        if (this.container) {
            this.container.scrollTop = this.container.scrollHeight;
        }
    }
    
    /**
     * HTML 转义
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    /**
     * 显示提示
     */
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

export const chatManager = new Chat();
export default chatManager;
