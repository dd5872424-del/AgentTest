/**
 * 内容资产管理
 */
import { CONFIG } from '../config.js';

const API_BASE = CONFIG.API_BASE_URL;

// 内容类型配置
const CONTENT_TYPES = {
    character: {
        name: '角色卡',
        icon: '👤',
        fields: [
            { key: 'name', label: '名称', type: 'text', required: true },
            { key: 'personality', label: '性格', type: 'textarea' },
            { key: 'scenario', label: '场景', type: 'textarea' },
            { key: 'first_message', label: '开场白', type: 'textarea' },
            { key: 'description', label: '描述', type: 'textarea' },
        ]
    },
    preset: {
        name: '预设',
        icon: '📝',
        fields: [
            { key: 'name', label: '名称', type: 'text', required: true },
            { key: 'system_prompt', label: '系统提示词', type: 'textarea', rows: 10 },
            { key: 'jailbreak', label: '越狱提示', type: 'textarea' },
        ]
    },
    world_info: {
        name: '世界观',
        icon: '🌍',
        fields: [
            { key: 'name', label: '名称', type: 'text', required: true },
            { key: 'keywords', label: '关键词', type: 'tags', placeholder: '输入后按 Enter 添加' },
            { key: 'content', label: '内容', type: 'textarea', rows: 6 },
            { key: 'priority', label: '优先级', type: 'number', default: 0 },
        ]
    },
    regex: {
        name: '正则脚本',
        icon: '🔧',
        fields: [
            { key: 'name', label: '名称', type: 'text', required: true },
            { key: 'find_regex', label: '查找正则', type: 'text', placeholder: '正则表达式' },
            { key: 'replace_string', label: '替换为', type: 'text' },
            { key: 'flags', label: '标志', type: 'text', default: 'gi' },
            { key: 'enabled', label: '启用', type: 'checkbox', default: true },
            { key: 'priority', label: '优先级', type: 'number', default: 0 },
        ]
    },
};

class ContentsManager {
    constructor() {
        this.currentType = 'character';
        this.items = [];
        this.modalEl = null;
        this.panelEl = null;
    }
    
    /**
     * 初始化内容管理器
     */
    init() {
        this.createPanel();
        this.bindEvents();
    }
    
    /**
     * 创建管理面板
     */
    createPanel() {
        this.panelEl = document.createElement('div');
        this.panelEl.className = 'contents-panel';
        this.panelEl.innerHTML = `
            <div class="contents-panel-header">
                <h2 class="contents-panel-title">📦 内容管理</h2>
                <button class="btn-icon" id="close-contents-panel">✕</button>
            </div>
            
            <div class="contents-tabs">
                ${Object.entries(CONTENT_TYPES).map(([type, config]) => `
                    <button class="contents-tab ${type === this.currentType ? 'active' : ''}" data-type="${type}">
                        ${config.icon} ${config.name}
                    </button>
                `).join('')}
            </div>
            
            <div class="contents-toolbar">
                <button class="btn btn-primary" id="add-content-btn">+ 新建</button>
                <input type="text" class="input" id="contents-search" placeholder="搜索...">
            </div>
            
            <div class="contents-list" id="contents-list">
                <!-- 内容列表 -->
            </div>
        `;
        
        this.panelEl.style.display = 'none';
        document.body.appendChild(this.panelEl);
        
        // 创建模态框
        this.createModal();
    }
    
    /**
     * 创建编辑模态框
     */
    createModal() {
        this.modalEl = document.createElement('div');
        this.modalEl.className = 'modal-overlay';
        this.modalEl.id = 'content-modal';
        this.modalEl.innerHTML = `
            <div class="modal" style="max-width: 600px;">
                <div class="modal-header">
                    <span class="modal-title" id="content-modal-title">编辑内容</span>
                    <button class="btn-icon" id="close-content-modal">✕</button>
                </div>
                <div class="modal-body" id="content-modal-body">
                    <!-- 动态表单 -->
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="cancel-content-btn">取消</button>
                    <button class="btn btn-danger" id="delete-content-btn" style="display: none;">删除</button>
                    <button class="btn btn-primary" id="save-content-btn">保存</button>
                </div>
            </div>
        `;
        document.body.appendChild(this.modalEl);
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 打开面板按钮（在侧边栏）
        const openBtn = document.getElementById('open-contents-btn');
        if (openBtn) {
            openBtn.addEventListener('click', () => this.show());
        }
        
        // 关闭面板
        document.getElementById('close-contents-panel')?.addEventListener('click', () => this.hide());
        
        // 标签切换
        this.panelEl.querySelectorAll('.contents-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.currentType = tab.dataset.type;
                this.updateTabs();
                this.loadItems();
            });
        });
        
        // 新建按钮
        document.getElementById('add-content-btn')?.addEventListener('click', () => this.openEditor(null));
        
        // 搜索
        document.getElementById('contents-search')?.addEventListener('input', (e) => {
            this.filterItems(e.target.value);
        });
        
        // 模态框事件
        document.getElementById('close-content-modal')?.addEventListener('click', () => this.closeModal());
        document.getElementById('cancel-content-btn')?.addEventListener('click', () => this.closeModal());
        document.getElementById('save-content-btn')?.addEventListener('click', () => this.saveItem());
        document.getElementById('delete-content-btn')?.addEventListener('click', () => this.deleteItem());
        
        // 点击背景关闭
        this.modalEl?.addEventListener('click', (e) => {
            if (e.target === this.modalEl) this.closeModal();
        });
    }
    
    /**
     * 显示面板
     */
    async show() {
        this.panelEl.style.display = 'flex';
        await this.loadItems();
    }
    
    /**
     * 隐藏面板
     */
    hide() {
        this.panelEl.style.display = 'none';
    }
    
    /**
     * 更新标签状态
     */
    updateTabs() {
        this.panelEl.querySelectorAll('.contents-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.type === this.currentType);
        });
    }
    
    /**
     * 加载内容列表
     */
    async loadItems() {
        const listEl = document.getElementById('contents-list');
        if (!listEl) return;
        
        listEl.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';
        
        try {
            const response = await fetch(`${API_BASE}/api/contents/${this.currentType}`);
            const data = await response.json();
            this.items = data.items || [];
            this.renderItems();
        } catch (error) {
            console.error('加载内容失败:', error);
            listEl.innerHTML = '<div style="color: var(--accent-pink); padding: 20px;">加载失败</div>';
        }
    }
    
    /**
     * 渲染内容列表
     */
    renderItems() {
        const listEl = document.getElementById('contents-list');
        if (!listEl) return;
        
        if (this.items.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state" style="padding: 40px;">
                    <div style="font-size: 32px; opacity: 0.5; margin-bottom: 10px;">
                        ${CONTENT_TYPES[this.currentType].icon}
                    </div>
                    <div>暂无${CONTENT_TYPES[this.currentType].name}</div>
                </div>
            `;
            return;
        }
        
        listEl.innerHTML = this.items.map(item => `
            <div class="content-item" data-id="${item.id}">
                <div class="content-item-icon">${CONTENT_TYPES[this.currentType].icon}</div>
                <div class="content-item-info">
                    <div class="content-item-name">${this.escapeHtml(item.data?.name || item.id)}</div>
                    <div class="content-item-meta">
                        <span class="tag">${item.id}</span>
                        ${item.tags?.map(t => `<span class="tag tag-cyan">${t}</span>`).join('') || ''}
                    </div>
                </div>
                <div class="content-item-actions">
                    <button class="btn-icon" data-action="edit" data-tooltip="编辑">✏️</button>
                    <button class="btn-icon" data-action="delete" data-tooltip="删除">🗑️</button>
                </div>
            </div>
        `).join('');
        
        // 绑定点击事件
        listEl.querySelectorAll('.content-item').forEach(item => {
            const id = item.dataset.id;
            
            item.querySelector('[data-action="edit"]')?.addEventListener('click', (e) => {
                e.stopPropagation();
                const contentItem = this.items.find(i => i.id === id);
                this.openEditor(contentItem);
            });
            
            item.querySelector('[data-action="delete"]')?.addEventListener('click', (e) => {
                e.stopPropagation();
                this.confirmDelete(id);
            });
            
            item.addEventListener('click', () => {
                const contentItem = this.items.find(i => i.id === id);
                this.openEditor(contentItem);
            });
        });
    }
    
    /**
     * 筛选内容
     */
    filterItems(keyword) {
        const listEl = document.getElementById('contents-list');
        if (!listEl) return;
        
        const lowerKeyword = keyword.toLowerCase();
        
        listEl.querySelectorAll('.content-item').forEach(item => {
            const name = item.querySelector('.content-item-name')?.textContent.toLowerCase() || '';
            const id = item.dataset.id.toLowerCase();
            const visible = name.includes(lowerKeyword) || id.includes(lowerKeyword);
            item.style.display = visible ? 'flex' : 'none';
        });
    }
    
    /**
     * 打开编辑器
     */
    openEditor(item) {
        const isNew = !item;
        const titleEl = document.getElementById('content-modal-title');
        const bodyEl = document.getElementById('content-modal-body');
        const deleteBtn = document.getElementById('delete-content-btn');
        
        if (titleEl) {
            titleEl.textContent = isNew ? 
                `新建${CONTENT_TYPES[this.currentType].name}` : 
                `编辑${CONTENT_TYPES[this.currentType].name}`;
        }
        
        if (deleteBtn) {
            deleteBtn.style.display = isNew ? 'none' : 'block';
        }
        
        // 生成表单
        const fields = CONTENT_TYPES[this.currentType].fields;
        const data = item?.data || {};
        
        bodyEl.innerHTML = `
            <form id="content-form">
                <div class="form-group">
                    <label class="form-label">ID <span style="color: var(--accent-pink);">*</span></label>
                    <input type="text" class="input" name="id" value="${item?.id || ''}" 
                        ${isNew ? '' : 'readonly'} required 
                        placeholder="唯一标识（英文/数字/下划线）">
                </div>
                
                ${fields.map(field => this.renderField(field, data[field.key])).join('')}
                
                <div class="form-group">
                    <label class="form-label">标签</label>
                    <input type="text" class="input" name="tags" value="${item?.tags?.join(', ') || ''}" 
                        placeholder="逗号分隔，如: fantasy, modern">
                </div>
            </form>
        `;
        
        // 存储当前编辑的 item
        this.editingItem = item;
        
        // 显示模态框
        this.modalEl.classList.add('active');
    }
    
    /**
     * 渲染表单字段
     */
    renderField(field, value) {
        const defaultValue = value ?? field.default ?? '';
        
        let inputHtml = '';
        
        switch (field.type) {
            case 'textarea':
                inputHtml = `<textarea class="input" name="${field.key}" rows="${field.rows || 3}" 
                    placeholder="${field.placeholder || ''}">${this.escapeHtml(String(defaultValue))}</textarea>`;
                break;
                
            case 'number':
                inputHtml = `<input type="number" class="input" name="${field.key}" value="${defaultValue}">`;
                break;
                
            case 'checkbox':
                inputHtml = `<label style="display: flex; align-items: center; gap: 8px;">
                    <input type="checkbox" name="${field.key}" ${defaultValue ? 'checked' : ''}>
                    <span>${field.label}</span>
                </label>`;
                return `<div class="form-group">${inputHtml}</div>`;
                
            case 'tags':
                const tags = Array.isArray(defaultValue) ? defaultValue.join(', ') : defaultValue;
                inputHtml = `<input type="text" class="input" name="${field.key}" value="${tags}" 
                    placeholder="${field.placeholder || '逗号分隔'}">`;
                break;
                
            default:
                inputHtml = `<input type="text" class="input" name="${field.key}" value="${this.escapeHtml(String(defaultValue))}" 
                    placeholder="${field.placeholder || ''}">`;
        }
        
        return `
            <div class="form-group">
                <label class="form-label">${field.label}${field.required ? ' <span style="color: var(--accent-pink);">*</span>' : ''}</label>
                ${inputHtml}
            </div>
        `;
    }
    
    /**
     * 关闭模态框
     */
    closeModal() {
        this.modalEl.classList.remove('active');
        this.editingItem = null;
    }
    
    /**
     * 保存内容
     */
    async saveItem() {
        const form = document.getElementById('content-form');
        if (!form) return;
        
        const formData = new FormData(form);
        const id = formData.get('id')?.trim();
        
        if (!id) {
            this.showToast('请填写 ID', 'error');
            return;
        }
        
        // 构建 data 对象
        const data = {};
        const fields = CONTENT_TYPES[this.currentType].fields;
        
        for (const field of fields) {
            let value = formData.get(field.key);
            
            if (field.type === 'checkbox') {
                value = form.querySelector(`[name="${field.key}"]`)?.checked ?? false;
            } else if (field.type === 'number') {
                value = parseInt(value) || 0;
            } else if (field.type === 'tags' && value) {
                value = value.split(',').map(s => s.trim()).filter(Boolean);
            }
            
            if (value !== null && value !== undefined && value !== '') {
                data[field.key] = value;
            }
        }
        
        // 处理标签
        const tagsStr = formData.get('tags');
        const tags = tagsStr ? tagsStr.split(',').map(s => s.trim()).filter(Boolean) : null;
        
        try {
            const response = await fetch(`${API_BASE}/api/contents/${this.currentType}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, data, tags }),
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '保存失败');
            }
            
            this.closeModal();
            await this.loadItems();
            this.showToast('保存成功', 'success');
        } catch (error) {
            console.error('保存失败:', error);
            this.showToast('保存失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 确认删除
     */
    confirmDelete(id) {
        if (!confirm(`确定删除 ${id} 吗？此操作不可恢复。`)) return;
        this.deleteItemById(id);
    }
    
    /**
     * 删除内容
     */
    async deleteItem() {
        if (!this.editingItem) return;
        
        if (!confirm(`确定删除 ${this.editingItem.id} 吗？此操作不可恢复。`)) return;
        
        await this.deleteItemById(this.editingItem.id);
        this.closeModal();
    }
    
    /**
     * 通过 ID 删除
     */
    async deleteItemById(id) {
        try {
            const response = await fetch(`${API_BASE}/api/contents/${this.currentType}/${id}`, {
                method: 'DELETE',
            });
            
            if (!response.ok) {
                throw new Error('删除失败');
            }
            
            await this.loadItems();
            this.showToast('删除成功', 'success');
        } catch (error) {
            console.error('删除失败:', error);
            this.showToast('删除失败: ' + error.message, 'error');
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
        
        requestAnimationFrame(() => toast.classList.add('show'));
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

export const contentsManager = new ContentsManager();
export default contentsManager;
