/**
 * 应用主入口
 */
import { sidebar } from './sidebar.js';
import { chatManager } from './chat.js';
import { api } from './api.js';
import { contentsManager } from './contents.js';

class App {
    constructor() {
        this.initialized = false;
    }
    
    /**
     * 初始化应用
     */
    async init() {
        if (this.initialized) return;
        
        console.log('🚀 AgentTest UI 启动中...');
        
        // 检查后端连接
        try {
            await api.health();
            console.log('✅ 后端连接正常');
        } catch (error) {
            console.error('❌ 后端连接失败:', error);
            this.showConnectionError();
            return;
        }
        
        // 初始化侧边栏
        sidebar.onSelect = (conv) => {
            chatManager.setConversation(conv);
            this.updateStatePanel(conv);
        };
        await sidebar.init();
        
        // 初始化聊天区域
        chatManager.init();
        
        // 初始化内容管理器
        contentsManager.init();
        
        // 绑定全局事件
        this.bindGlobalEvents();
        
        this.initialized = true;
        console.log('✅ AgentTest UI 初始化完成');
    }
    
    /**
     * 绑定全局事件
     */
    bindGlobalEvents() {
        // 状态面板切换
        const toggleStateBtn = document.getElementById('toggle-state-panel');
        const statePanel = document.getElementById('state-panel');
        
        if (toggleStateBtn && statePanel) {
            toggleStateBtn.addEventListener('click', () => {
                statePanel.classList.toggle('collapsed');
                toggleStateBtn.textContent = statePanel.classList.contains('collapsed') ? '📊' : '✕';
            });
        }
        
        // 刷新状态按钮
        const refreshStateBtn = document.getElementById('refresh-state-btn');
        if (refreshStateBtn) {
            refreshStateBtn.addEventListener('click', () => this.refreshState());
        }
        
        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + N: 新建会话
            if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
                e.preventDefault();
                sidebar.createNew();
            }
            
            // Escape: 关闭状态面板
            if (e.key === 'Escape' && statePanel && !statePanel.classList.contains('collapsed')) {
                statePanel.classList.add('collapsed');
            }
        });
    }
    
    /**
     * 更新状态面板
     */
    async updateStatePanel(conv) {
        const moodEl = document.getElementById('current-mood');
        const thoughtEl = document.getElementById('inner-thought');
        const characterEl = document.getElementById('character-info');
        const graphEl = document.getElementById('current-graph');
        
        if (!conv) {
            if (moodEl) moodEl.textContent = '-';
            if (thoughtEl) thoughtEl.textContent = '-';
            if (characterEl) characterEl.textContent = '-';
            if (graphEl) graphEl.textContent = '-';
            return;
        }
        
        if (graphEl) graphEl.textContent = conv.graph_name;
        
        try {
            const state = await api.state.get(conv.id);
            
            if (moodEl) moodEl.textContent = state.mood || '平静';
            if (thoughtEl) thoughtEl.textContent = state.inner_thought || '-';
            
            if (characterEl && state.character) {
                characterEl.innerHTML = `
                    <strong>${state.character.name || '未设置'}</strong><br>
                    <small>${state.character.personality || ''}</small>
                `;
            }
        } catch (error) {
            console.error('加载状态失败:', error);
        }
    }
    
    /**
     * 刷新当前状态
     */
    async refreshState() {
        if (sidebar.currentId) {
            const conv = sidebar.conversations.find(c => c.id === sidebar.currentId);
            await this.updateStatePanel(conv);
        }
    }
    
    /**
     * 显示连接错误
     */
    showConnectionError() {
        const container = document.getElementById('chat-messages');
        if (container) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <div class="empty-state-text" style="color: var(--accent-pink)">
                        无法连接到后端服务<br>
                        <small>请确保后端已启动: uvicorn api.main:app --port 8000</small>
                    </div>
                    <button class="btn btn-secondary" onclick="location.reload()">
                        重试
                    </button>
                </div>
            `;
        }
    }
}

// 创建应用实例
const app = new App();

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    app.init();
});

export default app;
