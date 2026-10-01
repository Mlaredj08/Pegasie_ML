/* Decision Tree UI – with CSV upload, delete buttons, and back/finish + AI suggestions */
(function(){
  // ----- Elements -----
  const selTree     = document.getElementById('treeSelect');
  const btnStart    = document.getElementById('btnStart');
  const stageStart  = document.getElementById('stage-start');
  const stageQ      = document.getElementById('stage-questions');
  const stageFin    = document.getElementById('stage-finish');
  const qWrap       = document.getElementById('questionContainer');
  const btnNext     = document.getElementById('btnNext');
  const btnBack     = document.getElementById('btnBack');
  const btnSkip     = document.getElementById('btnSkip');
  const btnFinish   = document.getElementById('btnFinish');
  const backToQ     = document.getElementById('btnBackToQuestions');
  const btnSubmit   = document.getElementById('btnSubmit');
  const qIndexEl    = document.getElementById('qIndex');
  const progress    = document.getElementById('progressBar');
  const preview     = document.getElementById('answersPreview');
  const treeList    = document.getElementById('treeList');
  const treeTitle   = document.getElementById('treeTitle');
  const treeVersion = document.getElementById('treeVersion');

  // Review modal elements
  const reviewModalEl   = document.getElementById('reviewModal');
  const reviewListEl    = document.getElementById('reviewList');
  const reviewNewEl     = document.getElementById('reviewNewQuestions');
  const reviewStatusEl  = document.getElementById('reviewStatus');
  const reviewApplyBtn  = document.getElementById('reviewApplyBtn');
  const reviewSubmitBtn = document.getElementById('reviewSubmitBtn');
  const reviewUserSel   = document.getElementById('reviewUserSel');
  const reviewUserInp   = document.getElementById('reviewUserInp');
  const reviewUserBtn   = document.getElementById('reviewUserBtn');

  // Testing / Debug elements
  const dbgText     = document.getElementById('debugAnswers');
  const dbgUser     = document.getElementById('debugUser');
  const btnStartTest= document.getElementById('btnStartTest');
  const btnRenderFinishPayload = document.getElementById('btnRenderFinish');

  // AI suggestion elements
  const btnSuggestTrees     = document.getElementById('btnSuggestTrees');
  const aiSuggestions       = document.getElementById('aiSuggestions');
  const aiSuggestionPreview = document.getElementById('aiSuggestionPreview');

  // CSV upload UI
  const csvFileInput   = document.getElementById('csvFileInput');
  const csvOutName     = document.getElementById('csvOutName');
  const csvStartId     = document.getElementById('csvStartId');
  const btnUploadCsv   = document.getElementById('btnUploadCsv');
  const btnSelectUploaded = document.getElementById('btnSelectUploaded');
  const csvJsonPreview = document.getElementById('csvJsonPreview');

  // ----- State -----
  let SESSION_ID = null;
  let TREE_NAME  = null;
  let LAST_NODE  = null;

  // ANSWERS: nodeId -> raw answer value (for backend + preview)
  let ANSWERS = {};

  // QUESTION_STATE: nodeId -> { answer, user, role }
  // Used to always restore the UI state of each question
  let QUESTION_STATE = {};

  // Ordered list of node ids in the order they were answered
  let PATH = [];

  let LAST_SAVED_TREE_NAME = null;
  let USERS = [];
  let LAST_SELECTED_USER = '';

  // Full tree JSON
  let TREE = null;

  // Snapshot for review modal auto-advance
  let ORIGINAL_ANSWERS_SNAPSHOT = null;

  // AI suggestions
  let LAST_AI_SUGGESTIONS = [];

  // Number of "real" questions (non-branch, non-end) minus skipped ones
  let NODE_COUNT = 0;

  // Skipped-node registry
  let skippedRegistry = {};

  // ----- Helpers -----
  function show(n){ n?.classList.remove('d-none'); }
  function hide(n){ n?.classList.add('d-none'); }
  function toast(m){ alert(m); }
  function parseCSV(s){ return (s||'').split(',').map(x=>x.trim()).filter(Boolean); }
  function pathToOrderedAnswers(){ return PATH.map(id => ({ id, answer: ANSWERS[id] })); }

  function parseJsonSafe(text){
    try{ return JSON.parse(text); }catch{ return null; }
  }

  function getSelectedUser(){
    const sel = (reviewUserSel?.value || '').trim();
    if (sel) return sel;
    if (LAST_SELECTED_USER) return LAST_SELECTED_USER;
    const first = (USERS && USERS.length>0) ? USERS[0].name : '';
    if (first){
      LAST_SELECTED_USER = first;
      if (reviewUserSel) reviewUserSel.value = first;
    }
    return first;
  }

  function renderReviewUserOptions(){
    if (!reviewUserSel) return;
    reviewUserSel.innerHTML = '<option value="">— Select user —</option>' + (USERS||[]).map(obj=>{
      const name = (obj && obj.name) || '';
      const role = (obj && obj.role) || '';
      const label = role ? `${name}, ${role}` : name;
      return `<option value="${name}">${label}</option>`;
    }).join('');
    if (LAST_SELECTED_USER){
      const exists = (USERS||[]).some(u=>u && u.name===LAST_SELECTED_USER);
      if (exists) reviewUserSel.value = LAST_SELECTED_USER;
    }
  }

  function deepEqual(a,b){
    if (a===b) return true;
    if (Array.isArray(a) && Array.isArray(b)){
      if (a.length!==b.length) return false;
      for(let i=0;i<a.length;i++){ if(!deepEqual(a[i],b[i])) return false; }
      return true;
    }
    if (typeof a==='object' && a && typeof b==='object' && b){
      const ka = Object.keys(a), kb = Object.keys(b);
      if (ka.length!==kb.length) return false;
      for(const k of ka){ if(!deepEqual(a[k], b[k])) return false; }
      return true;
    }
    return false;
  }

  // Auto-run a session using a provided answers map. If an answer is missing, stop and resume normal questioning.
  async function autoRunWithAnswers(answersMap, answeringUser){
    if (!selTree.value){ toast('Select a tree first'); return; }
    if (!SESSION_ID || TREE_NAME !== selTree.value){
      await startSession(selTree.value);
    }
    if (!SESSION_ID) return;

    while (LAST_NODE && answersMap && Object.prototype.hasOwnProperty.call(answersMap, LAST_NODE.id)){
      const entry = answersMap[LAST_NODE.id];
      const isObj = entry && typeof entry === 'object' && !Array.isArray(entry);
      const ansVal = isObj && Object.prototype.hasOwnProperty.call(entry, 'value') ? entry.value : entry;
      const userForThis = isObj && entry.answering_user ? entry.answering_user : (answeringUser||'debug');
      const tsForThis = isObj && entry.timestamp ? entry.timestamp : new Date().toISOString();
      let roleForThis = isObj && entry.user_role ? entry.user_role : '';
      if(!roleForThis && userForThis){
        const found = (USERS||[]).find(u=>u && u.name===userForThis);
        roleForThis = found?.role || '';
      }

      ANSWERS[LAST_NODE.id] = ansVal;
      QUESTION_STATE[LAST_NODE.id] = {
        answer: ansVal,
        user: userForThis,
        role: roleForThis
      };

      PATH.push(LAST_NODE.id);
      await sendAnswer(LAST_NODE.id, ansVal, userForThis, tsForThis, roleForThis);
    }
  }

  // Render a list of trees with a trash button
  function renderTreeList(items){
    if (!treeList) return;
    treeList.innerHTML = '';
    if (!items || !items.length){
      treeList.innerHTML = '<div class="text-muted small">No trees yet. Upload one below.</div>';
      return;
    }

    const ul = document.createElement('ul');
    ul.className = 'list-group';
    items.forEach(name => {
      const li = document.createElement('li');
      li.className = 'list-group-item d-flex align-items-center justify-content-between';

      const left = document.createElement('div');
      left.className = 'd-flex align-items-center gap-2';

      const a = document.createElement('a');
      a.href = '#';
      a.textContent = name;
      a.onclick = (e)=>{ e.preventDefault(); selTree.value = name; btnStart.disabled = false; };
      left.appendChild(a);

      const right = document.createElement('div');
      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-sm btn-outline-danger';
      delBtn.title = 'Delete this tree';
      delBtn.innerHTML = '🗑️';
      delBtn.onclick = async ()=>{
        if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
        try{
          const res = await fetch(`/trees/${encodeURIComponent(name)}`, { method: 'DELETE' });
          const data = await res.json();
          if (!res.ok){ alert(data?.error || 'Delete failed'); return; }
          await fetchTrees();
          if (selTree.value === name){ selTree.value = ''; btnStart.disabled = true; }
        }catch(e){ alert('Delete failed'); }
      };
      right.appendChild(delBtn);

      li.append(left, right);
      ul.appendChild(li);
    });
    treeList.appendChild(ul);
  }

  async function fetchTrees(){
    try{
      const res = await fetch('/trees');
      const arr = await res.json();
      selTree.innerHTML = '<option value="" disabled selected>— Select a tree —</option>' +
        (arr||[]).map(x=>`<option value="${x}">${x}</option>`).join('');
      renderTreeList(arr||[]);
      if (LAST_SAVED_TREE_NAME) {
        const opt = Array.from(selTree.options).find(o=>o.value===LAST_SAVED_TREE_NAME);
        if (opt) { selTree.value = LAST_SAVED_TREE_NAME; btnStart.disabled = false; }
      }
    }catch(e){
      selTree.innerHTML = '<option value="" disabled>— No trees —</option>';
      renderTreeList([]);
    }
    btnStart.disabled = !selTree.value;
  }

  // expose so we can call later if needed
  window.__dt_fetchTrees = fetchTrees;

  function setProgress(){
    const idx = PATH.length;
    qIndexEl.textContent = `${idx}/${NODE_COUNT || '—'}`;
    const pct = NODE_COUNT ? Math.round((idx/Math.max(1,NODE_COUNT))*100) : 0;
    progress.style.width = `${pct}%`;
  }

  function renderStart(){ hide(stageQ); hide(stageFin); show(stageStart); }
  function renderQuestions(){ hide(stageStart); hide(stageFin); show(stageQ); setProgress(); }
  function renderFinish(payload){
    hide(stageStart); hide(stageQ); show(stageFin);
    preview.textContent = JSON.stringify(payload || {answers: ANSWERS}, null, 2);
  }

  function el(tag, attrs={}, ...kids){
    const n = document.createElement(tag);
    for (const [k,v] of Object.entries(attrs)){
      if (k==='class') n.className=v;
      else if (k==='html') n.innerHTML=v;
      else if (k.startsWith('on') && typeof v==='function') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k,v);
    }
    for (const k of kids){
      if (k==null) continue;
      if (typeof k==='string') n.appendChild(document.createTextNode(k));
      else n.appendChild(k);
    }
    return n;
  }

  async function fetchUsers(){
    try{
      const res = await fetch('/dt/users');
      const data = await res.json();
      if(res.ok){ USERS = Array.isArray(data.users) ? data.users : []; }
      else { USERS = []; }
    }catch{ USERS = []; }
  }

  async function startSession(name){
    TREE_NAME = name;
    SESSION_ID = null;
    ANSWERS = {};
    QUESTION_STATE = {};
    PATH = [];
    NODE_COUNT = 0;

    const res = await fetch('/dt/start', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ tree_name: name })
    });
    const data = await res.json();
    if(!res.ok){
      toast(data?.error||'Failed to start');
      return;
    }
    SESSION_ID = data.session_id;

    try{
      const resTree = await fetch(`/get_tree?name=${encodeURIComponent(name)}`);
      const tree = await resTree.json();
      TREE = tree;
      NODE_COUNT = Object.values(tree.nodes || {})
        .filter(node => node.type !== 'branch' && node.type !== 'end').length;
      if (treeTitle)   treeTitle.textContent   = tree?.meta?.title || name;
      if (treeVersion) treeVersion.textContent = `v${tree?.meta?.version || '—'}`;
    }catch(e){}

    await fetchUsers();

    if (data.node){
      renderQuestions();
      renderNodePayload(data.node);
    }else if (data.done){
      renderFinish({answers: data.answers, profile: data.profile});
    }
  }

  async function sendAnswer(node_id, answer, answering_user, timestamp, user_role){
    const res = await fetch('/dt/answer', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: SESSION_ID, node_id, answer, answering_user, user_role, timestamp })
    });
    const data = await res.json();
    if(!res.ok){
      toast(data?.error||'Failed to send answer');
      return;
    }
    if (data.done){
      renderFinish({answers: data.answers, profile: data.profile});
      return;
    }
    if (data.node){
      const previous_q = node_id;
      const current_q = data.node.id;
      const tree_nodes = TREE.nodes;
      const skipped_registry = calculateSkipped(previous_q, current_q, tree_nodes);
      if (skipped_registry != {}){
        const total_skipped = Object.values(skipped_registry).reduce((a, b) => a + b, 0);
        NODE_COUNT = NODE_COUNT - total_skipped;
      }
      setProgress();
      renderQuestions();
      renderNodePayload(data.node);
    }
  }

  async function rewindSession(){
    const res = await fetch('/dt/rewind', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: SESSION_ID, answers: pathToOrderedAnswers() })
    });
    const data = await res.json();
    if(!res.ok){
      toast(data?.error||'Failed to rewind');
      return;
    }
    if (data.node){
      renderQuestions();
      renderNodePayload(data.node);
    } else if (data.done){
      renderFinish({answers: data.answers, profile: data.profile});
    }
    setProgress();
  }

  function renderNodePayload(node){
    qWrap.innerHTML = '';
    LAST_NODE = node;

    if (!node){
      btnNext.classList.add('d-none');
      btnFinish.classList.remove('d-none');
      return;
    }

    const prompt = el('div', {class:'mb-2'},
      el('h2', {class:'h5 mb-1'}, node.prompt || node.id || 'Question'),
      el('div', {class:'muted small'}, `Node: ${node.id} · Type: ${node.type}`)
    );
    const form = el('div');

    // Remove any previously mounted footer user selector
    document.getElementById('footerUserWrap')?.remove();
    const userWrap = el('div', {id:'footerUserWrap', class:'d-flex flex-wrap gap-2 align-items-center'});
    const userSel = el('select', {class:'form-select', style:'max-width: 260px;'});

    const renderUserOptions = ()=>{
      userSel.innerHTML = '<option value="">— Select user —</option>' + (USERS||[]).map(obj=>{
        const name = (obj && obj.name) || '';
        const role = (obj && obj.role) || '';
        const label = role ? `${name}, ${role}` : name;
        return `<option value="${name}">${label}</option>`;
      }).join('');
      if (LAST_SELECTED_USER){
        const exists = (USERS||[]).some(u=>u && u.name===LAST_SELECTED_USER);
        if (exists) userSel.value = LAST_SELECTED_USER;
      }
    };
    renderUserOptions();

    const savedState = QUESTION_STATE[node.id];
    if (savedState && savedState.user){
      userSel.value = savedState.user;
      LAST_SELECTED_USER = savedState.user;
    }

    userSel.addEventListener('change', ()=>{
      if (userSel.value) LAST_SELECTED_USER = userSel.value;
    });

    const userInp = el('input', {
      type:'text',
      class:'form-control',
      placeholder:'Add user (Name, Role)…',
      style:'max-width: 240px;'
    });
    const userBtn = el('button', {class:'btn btn-outline-secondary', type:'button', style:'white-space:nowrap;'}, 'Add');

    userBtn.addEventListener('click', async ()=>{
      const raw = userInp.value.trim();
      if(!raw) return;
      if(!raw.includes(',')) {
        toast('Format must be: Name, Role');
        return;
      }
      const parts = raw.split(',');
      const name = (parts[0]||'').trim();
      const role = (parts.slice(1).join(',')||'').trim();
      if(!name || !role){
        toast('Both name and role are required (Name, Role)');
        return;
      }
      const res = await fetch('/dt/users', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ name, role, tree_name: TREE_NAME })
      });
      const data = await res.json();
      if(!res.ok){
        return toast(data?.error||'Failed to add user');
      }
      USERS = data.users || [];
      renderUserOptions();
      userSel.value = name;
      LAST_SELECTED_USER = name;
      userInp.value='';
    });

    userWrap.append(userSel, userInp, userBtn);

    const bottomBar = document.querySelector('.bottom-bar');
    const rightControls = bottomBar?.querySelector('.d-flex.gap-2');
    if (bottomBar && rightControls){
      bottomBar.insertBefore(userWrap, rightControls);
    }

    // ----- Inputs -----
    const saved = savedState ? savedState.answer : undefined;
    let getter = null;

    function inputYesNo(){
      const group = `yn-${node.id}`;
      const idYes = `yn-yes-${node.id}`;
      const idNo  = `yn-no-${node.id}`;
      const yes = el('input',{type:'radio',class:'btn-check',name:group,id:idYes,autocomplete:'off'});
      const lYes= el('label',{class:'btn btn-outline-primary me-2',for:idYes},'Yes');
      const no  = el('input',{type:'radio',class:'btn-check',name:group,id:idNo,autocomplete:'off'});
      const lNo = el('label',{class:'btn btn-outline-primary',for:idNo},'No');
      if(saved===true) yes.checked=true;
      if(saved===false) no.checked=true;
      form.append(yes, lYes, no, lNo);
      return ()=> yes.checked ? true : (no.checked ? false : null);
    }

    function inputText(){
      const ta = el('textarea',{class:'form-control',rows:'4',placeholder:'Type your answer…'});
      if(typeof saved==='string') ta.value = saved;
      form.append(ta);
      return ()=> ta.value.trim();
    }

    function inputList(){
      const inp = el('input',{
        type:'text',
        class:'form-control',
        placeholder:'Comma-separated values'
      });
      if(Array.isArray(saved)) inp.value = saved.join(', ');
      const help = el('div',{class:'form-text'},'Tip: press Enter or use commas to separate items.');
      form.append(inp,help);
      return ()=> parseCSV(inp.value);
    }

    function inputSingleSelect(){
      const opts = node.options || [];
      if(!opts.length){ return inputText(); }
      const sel = el('select',{class:'form-select'});
      sel.innerHTML = '<option value="">— Select —</option>' +
        opts.map(o=>`<option value="${o}">${o}</option>`).join('');
      if(typeof saved==='string') sel.value=saved;
      form.append(sel);
      return ()=> sel.value||null;
    }

    function inputMultiSelect(){
      const opts = node.options || [];
      if(!opts.length){ return inputList(); }
      const box = el('div',{class:'d-flex flex-wrap gap-2'});
      const picks = new Set(Array.isArray(saved)? saved: []);
      opts.forEach((o,i)=>{
        const id = `ms-${node.id}-${i}`;
        const chk = el('input',{type:'checkbox',class:'btn-check',id});
        if(picks.has(o)) chk.checked=true;
        const lab = el('label',{class:'btn btn-outline-secondary',for:id},o);
        box.append(chk,lab);
      });
      form.append(box);
      return ()=>{
        const out=[];
        box.querySelectorAll('input[type="checkbox"]').forEach((c,idx)=>{
          if(c.checked) out.push((node.options||[])[idx]);
        });
        return out;
      };
    }

    switch(node.type){
      case 'yes_no':        getter = inputYesNo(); break;
      case 'text':          getter = inputText(); break;
      case 'list':          getter = inputList(); break;
      case 'single_select': getter = inputSingleSelect(); break;
      case 'multi_select':  getter = inputMultiSelect(); break;
      case 'end':
        btnNext.classList.add('d-none');
        btnFinish.classList.remove('d-none');
        qWrap.append(prompt);
        return;
      default:
        getter = inputText();
    }

    qWrap.append(prompt, form);

    btnNext.onclick = async ()=>{
      const selUser = userSel.value;
      if(!selUser){
        return toast('Please select at least one user.');
      }
      const val = getter();
      if(val===null || (Array.isArray(val) && val.length===0)){
        return toast('Please answer or click Skip');
      }
      const role = ((USERS||[]).find(u=>u && u.name===selUser)?.role)||'';

      QUESTION_STATE[node.id] = {
        answer: val,
        user: selUser,
        role: role
      };

      ANSWERS[node.id] = val;
      PATH.push(node.id);
      qWrap.innerHTML = '';
      await sendAnswer(node.id, val, selUser, new Date().toISOString(), role);
    };

    btnSkip.onclick = async ()=>{
      const selUser = userSel.value;
      if(!selUser){
        return toast('Please select at least one user.');
      }
      const role = ((USERS||[]).find(u=>u && u.name===selUser)?.role)||'';
      const fallback =
        node.type==='yes_no'
          ? false
          : (node.type==='list'||node.type==='multi_select' ? [] : '');

      QUESTION_STATE[node.id] = {
        answer: fallback,
        user: selUser,
        role: role
      };

      ANSWERS[node.id] = fallback;
      PATH.push(node.id);
      qWrap.innerHTML = '';
      await sendAnswer(node.id, fallback, selUser, new Date().toISOString(), role);
    };

    btnBack.onclick = async ()=>{
      if (!SESSION_ID) return;
      if (PATH.length === 0){
        toast('No previous question.');
        return;
      }
      const lastId = PATH.pop();
      delete ANSWERS[lastId]; // keep QUESTION_STATE so UI can repopulate if revisited
      await rewindSession();
    };
  }

  // ----- Review Modal Logic -----
  let reviewModal = null;
  function getBootstrapModal(){
    if (!reviewModal && reviewModalEl && window.bootstrap){
      reviewModal = new bootstrap.Modal(reviewModalEl);
    }
    return reviewModal;
  }

  function renderEditorForType(node, value){
    const wrap = document.createElement('div');
    wrap.className = 'mt-1';
    const inputId = `rev-${node.id}`;
    switch(node.type){
      case 'yes_no':{
        const group = `rev-yn-${node.id}`;
        const idYes = `${inputId}-yes`;
        const idNo  = `${inputId}-no`;
        const yes = el('input',{type:'radio',class:'btn-check',name:group,id:idYes});
        const lYes= el('label',{class:'btn btn-sm btn-outline-primary me-2',for:idYes},'Yes');
        const no  = el('input',{type:'radio',class:'btn-check',name:group,id:idNo});
        const lNo = el('label',{class:'btn btn-sm btn-outline-primary',for:idNo},'No');
        if(value===true) yes.checked=true;
        if(value===false) no.checked=true;
        wrap.append(yes,lYes,no,lNo);
        break;
      }
      case 'text':{
        const ta = el('textarea',{id:inputId,class:'form-control form-control-sm',rows:'2'});
        if(typeof value==='string') ta.value=value;
        wrap.append(ta);
        break;
      }
      case 'list':{
        const inp = el('input',{
          id:inputId,
          type:'text',
          class:'form-control form-control-sm',
          placeholder:'Comma-separated'
        });
        if(Array.isArray(value)) inp.value = value.join(', ');
        wrap.append(inp);
        break;
      }
      case 'single_select':{
        const sel = el('select',{id:inputId,class:'form-select form-select-sm'});
        const opts = node.options||[];
        sel.innerHTML = '<option value="">— Select —</option>' +
          opts.map(o=>`<option value="${o}">${o}</option>`).join('');
        if(typeof value==='string') sel.value=value;
        wrap.append(sel);
        break;
      }
      case 'multi_select':{
        const box = el('div',{id:inputId,class:'d-flex flex-wrap gap-2'});
        const picks = new Set(Array.isArray(value)? value: []);
        (node.options||[]).forEach((o,i)=>{
          const cid = `${inputId}-${i}`;
          const chk = el('input',{type:'checkbox',class:'btn-check',id:cid});
          if(picks.has(o)) chk.checked=true;
          const lab = el('label',{class:'btn btn-sm btn-outline-secondary',for:cid},o);
          box.append(chk,lab);
        });
        wrap.append(box);
        break;
      }
      default:{
        const inp = el('input',{id:inputId,type:'text',class:'form-control form-control-sm'});
        if(value!=null) inp.value = String(value);
        wrap.append(inp);
      }
    }
    return wrap;
  }

  function readEditorValue(node){
    const inputId = `rev-${node.id}`;
    switch(node.type){
      case 'yes_no':{
        const yes = document.getElementById(`${inputId}-yes`);
        const no  = document.getElementById(`${inputId}-no`);
        return (yes?.checked ? true : (no?.checked ? false : null));
      }
      case 'text':{
        const ta = document.getElementById(inputId);
        return (ta?.value||'').trim();
      }
      case 'list':{
        const inp = document.getElementById(inputId);
        return parseCSV(inp?.value||'');
      }
      case 'single_select':{
        const sel = document.getElementById(inputId);
        return sel?.value||null;
      }
      case 'multi_select':{
        const box = document.getElementById(inputId);
        const out=[];
        if(box){
          const checks = box.querySelectorAll('input[type="checkbox"]');
          const opts = (node && Array.isArray(node.options))
            ? node.options
            : ((TREE?.nodes?.[node.id]?.options)||[]);
          checks.forEach((c,idx)=>{
            if(c.checked) out.push(opts[idx]);
          });
        }
        return out;
      }
      default:{
        const inp = document.getElementById(inputId);
        return (inp?.value||'');
      }
    }
  }

  function renderReviewList(){
    if(!TREE || !TREE.nodes) return;
    reviewListEl.innerHTML='';
    PATH.forEach((id)=>{
      const node = TREE.nodes[id];
      if(!node) return;
      const li = document.createElement('li');
      li.className = 'list-group-item';
      const title = el('div',{class:'fw-semibold'}, node.prompt || id);
      const meta = el('div',{class:'small text-muted'}, `Node: ${id} · Type: ${node.type}`);
      const editor = renderEditorForType(node, ANSWERS[id]);
      li.append(title, meta, editor);
      reviewListEl.appendChild(li);
    });
  }

  async function rewindForModal(orderedAnswers){
    try{
      const res = await fetch('/dt/rewind', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ session_id: SESSION_ID, answers: orderedAnswers })
      });
      const data = await res.json();
      if(!res.ok){
        reviewStatusEl.textContent = (data?.error||'Failed to rewind');
        return null;
      }
      return data;
    }catch(e){
      reviewStatusEl.textContent='Failed to rewind';
      return null;
    }
  }

  function renderModalNode(node){
    reviewNewEl.innerHTML='';
    if(!node){
      reviewStatusEl.innerHTML = '<div class="alert alert-success py-2">All questions answered. You can Submit.</div>';
      return;
    }
    const prompt = el('div', {class:'mb-2'},
      el('h2', {class:'h6 mb-1'}, node.prompt || node.id || 'Question'),
      el('div', {class:'muted small'}, `Node: ${node.id} · Type: ${node.type}`)
    );
    const form = renderEditorForType(node, undefined);
    const btn = el('button',{class:'btn btn-sm btn-brand mt-2', type:'button'},'Next');
    btn.addEventListener('click', async ()=>{
      const selUser = getSelectedUser();
      if(!selUser){
        return toast('Please select at least one user in the main UI before continuing.');
      }
      const role = ((USERS||[]).find(u=>u && u.name===selUser)?.role)||'';
      let val = (function(){
        const n = Object.assign({}, node);
        return readEditorValue(n);
      })();
      if(val===null || (Array.isArray(val) && val.length===0)){
        return toast('Please answer.');
      }

      ANSWERS[node.id] = val;
      if(!PATH.includes(node.id)) PATH.push(node.id);

      QUESTION_STATE[node.id] = {
        answer: val,
        user: selUser,
        role: role
      };

      const res = await fetch('/dt/answer',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          session_id: SESSION_ID,
          node_id: node.id,
          answer: val,
          answering_user: selUser,
          user_role: role,
          timestamp: new Date().toISOString()
        })
      });
      const data = await res.json();
      if(!res.ok){
        return toast(data?.error||'Failed to send answer');
      }
      continueWithAutoAnswers(data);
    });
    reviewNewEl.append(prompt, form, btn);
  }

  async function continueWithAutoAnswers(payload){
    if (!payload) return;
    if (payload.answers && typeof payload.answers === 'object'){
      ANSWERS = payload.answers;
      PATH = PATH.filter(id => Object.prototype.hasOwnProperty.call(ANSWERS, id));
      Object.keys(ANSWERS).forEach(id=>{
        const existing = QUESTION_STATE[id] || {};
        QUESTION_STATE[id] = {
          answer: ANSWERS[id],
          user: existing.user || '',
          role: existing.role || ''
        };
      });
    }
    if (payload.done){
      renderReviewList();
      reviewNewEl.innerHTML='';
      reviewStatusEl.innerHTML = '<div class="alert alert-success py-2">All questions answered. You can Submit.</div>';
      return;
    }
    const node = payload.node;
    if (!node){
      reviewNewEl.innerHTML='';
      reviewStatusEl.innerHTML = '<div class="alert alert-success py-2">All questions answered. You can Submit.</div>';
      return;
    }
    const nid = node.id;
    const originalVal = ORIGINAL_ANSWERS_SNAPSHOT ? ORIGINAL_ANSWERS_SNAPSHOT[nid] : undefined;
    if (typeof originalVal !== 'undefined'){
      const selUser = getSelectedUser();
      if(!selUser){
        return renderModalNode(node);
      }
      const role = ((USERS||[]).find(u=>u && u.name===selUser)?.role)||'';

      ANSWERS[nid] = originalVal;
      if(!PATH.includes(nid)) PATH.push(nid);

      QUESTION_STATE[nid] = {
        answer: originalVal,
        user: selUser,
        role: role
      };

      const res = await fetch('/dt/answer',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          session_id: SESSION_ID,
          node_id: nid,
          answer: originalVal,
          answering_user: selUser,
          user_role: role,
          timestamp: new Date().toISOString()
        })
      });
      const data = await res.json();
      if(!res.ok){
        return toast(data?.error||'Failed to send answer');
      }
      if (data.answers && typeof data.answers === 'object'){
        ANSWERS = data.answers;
        PATH = PATH.filter(id => Object.prototype.hasOwnProperty.call(ANSWERS, id));
      }
      renderReviewList();
      return continueWithAutoAnswers(data);
    }
    renderModalNode(node);
  }

  function openReviewModal(){
    if(!SESSION_ID){
      return toast('No active session');
    }
    ORIGINAL_ANSWERS_SNAPSHOT = Object.assign({}, ANSWERS);
    renderReviewUserOptions();
    reviewUserBtn?.addEventListener('click', async ()=>{
      const raw = (reviewUserInp?.value||'').trim();
      if(!raw) return;
      if(!raw.includes(',')) {
        return toast('Format must be: Name, Role');
      }
      const parts = raw.split(',');
      const name = (parts[0]||'').trim();
      const role = (parts.slice(1).join(',')||'').trim();
      if(!name || !role){
        return toast('Both name and role are required (Name, Role)');
      }
      try{
        const res = await fetch('/dt/users', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ name, role, tree_name: TREE_NAME })
        });
        const data = await res.json();
        if(!res.ok){
          return toast(data?.error||'Failed to add user');
        }
        USERS = data.users || [];
        LAST_SELECTED_USER = name;
        renderReviewUserOptions();
        reviewUserSel.value = name;
        reviewUserInp.value='';
      }catch(e){
        toast('Failed to add user');
      }
    }, { once: true });

    reviewUserSel?.addEventListener('change', ()=>{
      if (reviewUserSel.value) LAST_SELECTED_USER = reviewUserSel.value;
    });

    renderReviewList();
    reviewNewEl.innerHTML='';
    reviewStatusEl.textContent='';
    getBootstrapModal()?.show();
  }

  reviewApplyBtn?.addEventListener('click', async ()=>{
    if(!TREE || !TREE.nodes) return;
    let cutoffIdx = PATH.length;
    const prefix = [];
    for(let i=0;i<PATH.length;i++){
      const id = PATH[i];
      const node = TREE.nodes[id];
      if(!node) continue;
      const edited = readEditorValue(node);
      const isCleared =
        (edited===null) ||
        (typeof edited==='string' && !edited.trim()) ||
        (Array.isArray(edited) && edited.length===0);
      const original = ANSWERS[id];
      if(isCleared){
        cutoffIdx = Math.min(cutoffIdx, i);
        break;
      }
      if(!deepEqual(edited, original)){
        cutoffIdx = Math.min(cutoffIdx, i);
        prefix.push({ id, answer: edited });
        break;
      }
      prefix.push({ id, answer: original });
    }

    if (cutoffIdx === PATH.length){
      renderReviewList();
      reviewStatusEl.innerHTML = '<div class="alert alert-secondary py-2">No changes detected.</div>';
      return;
    }

    reviewStatusEl.innerHTML = '<div class="alert alert-info py-2">Recomputing flow…</div>';
    const data = await rewindForModal(prefix);
    if(!data) return;
    if (data.answers && typeof data.answers === 'object'){
      ANSWERS = data.answers;
      const base = prefix.map(o=>o.id).filter(id => Object.prototype.hasOwnProperty.call(ANSWERS, id));
      PATH = base;
      PATH.forEach(id=>{
        const existing = QUESTION_STATE[id] || {};
        QUESTION_STATE[id] = {
          answer: ANSWERS[id],
          user: existing.user || '',
          role: existing.role || ''
        };
      });
    }
    renderReviewList();
    if(data.node){
      continueWithAutoAnswers(data);
    } else if(data.done){
      renderReviewList();
      reviewNewEl.innerHTML='';
      reviewStatusEl.innerHTML = '<div class="alert alert-success py-2">All questions answered. You can Submit.</div>';
    }
  });

  reviewSubmitBtn?.addEventListener('click', async ()=>{
    try{
      const res = await fetch(`/dt/save_profile/${SESSION_ID}`);
      const data = await res.json();
      preview.textContent = JSON.stringify(data, null, 2);
      toast('Profile retrieved from backend session.');
      getBootstrapModal()?.hide();
      window.location.href = "/";
    }catch(e){
      toast('Failed to submit');
    }
  });

  // ----- CSV Upload → server conversion & save -----
  btnUploadCsv?.addEventListener('click', async ()=>{
    const file = csvFileInput?.files?.[0];
    if (!file){
      return toast('Please select a CSV file.');
    }
    const outName = (csvOutName.value || '').trim();
    if (!outName){
      return toast('Please provide a JSON file name to save (e.g., my_tree.json).');
    }

    const fd = new FormData();
    fd.append('file', file);
    fd.append('file_name', outName);
    fd.append('start_id', (csvStartId.value || '').trim());

    try{
      const res = await fetch('/trees/upload_csv', { method:'POST', body: fd });
      const data = await res.json();
      if (!res.ok){
        toast(data?.error || 'Upload failed');
        return;
      }
      LAST_SAVED_TREE_NAME = data.saved_name;
      csvJsonPreview.textContent = JSON.stringify(data.tree, null, 2);
      await fetchTrees();
      const opt = Array.from(selTree.options).find(o=>o.value===LAST_SAVED_TREE_NAME);
      if (opt){
        selTree.value = LAST_SAVED_TREE_NAME;
        btnStart.disabled = false;
      }
    }catch(e){
      console.error(e);
      toast('Upload failed');
    }
  });

  // ----- AI Suggestions -----
  function renderAiSuggestions(list){
    if (!aiSuggestions) return;
    aiSuggestions.innerHTML = '';
    aiSuggestionPreview.textContent = '';
    if (!list || !list.length){
      aiSuggestions.innerHTML = '<div class="text-muted small">No suggestions received.</div>';
      return;
    }
    list.forEach((sug, idx)=>{
      const card = document.createElement('div');
      card.className = 'border rounded p-2 mb-2 d-flex justify-content-between align-items-center';

      const left = document.createElement('div');
      const title = document.createElement('div');
      title.className = 'fw-semibold';
      title.textContent = sug.objective || `Suggested tree ${idx+1}`;
      const meta = document.createElement('div');
      const nodesCount = sug.tree && sug.tree.nodes ? Object.keys(sug.tree.nodes).length : 0;
      meta.className = 'small text-muted';
      meta.textContent = `File: ${sug.file_name || 'suggested_'+(idx+1)+'.json'} · Questions: ${nodesCount}`;
      left.appendChild(title);
      left.appendChild(meta);

      const right = document.createElement('div');
      const btnPrev = document.createElement('button');
      btnPrev.className = 'btn btn-sm btn-outline-secondary me-2';
      btnPrev.textContent = 'Preview';
      btnPrev.onclick = ()=>{
        aiSuggestionPreview.textContent = JSON.stringify(sug.tree, null, 2);
      };

      const btnSave = document.createElement('button');
      btnSave.className = 'btn btn-sm btn-primary';
      btnSave.textContent = 'Save & load';
      btnSave.onclick = async ()=>{
        try{
          const res = await fetch('/dt/save_suggested_tree', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              file_name: sug.file_name || `suggested_${idx+1}.json`,
              tree: sug.tree
            })
          });
          const data = await res.json();
          if (!res.ok){
            toast(data?.error || 'Failed to save tree.');
            return;
          }
          toast('Tree saved. Refreshing list...');
          await fetchTrees();
        }catch(e){
          toast('Failed to save tree.');
        }
      };

      right.appendChild(btnPrev);
      right.appendChild(btnSave);
      card.appendChild(left);
      card.appendChild(right);
      aiSuggestions.appendChild(card);
    });
  }

  btnSuggestTrees?.addEventListener('click', async ()=>{
    if (!SESSION_ID){
      return toast('No questionnaire session found.');
    }
    try{
      const res = await fetch(`/dt/suggest_trees/${SESSION_ID}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (!res.ok){
        toast(data?.error || 'AI suggestion failed');
        return;
      }
      LAST_AI_SUGGESTIONS = JSON.parse(data).suggestions || [];
      renderAiSuggestions(LAST_AI_SUGGESTIONS);
    }catch(e){
      console.error(e);
      toast('AI suggestion failed');
    }
  });

  // ----- Wire up -----
  selTree?.addEventListener('change', ()=>{
    btnStart.disabled = !selTree.value;
  });

  btnStart?.addEventListener('click', async ()=>{
    if (!selTree.value){
      return toast('Select a tree first');
    }
    const raw = dbgText?.value?.trim();
    if (raw){
      const parsed = parseJsonSafe(raw);
      if (parsed){
        let answersMap = parsed;
        if (parsed && typeof parsed==='object' && parsed.answers && typeof parsed.answers==='object'){
          answersMap = parsed.answers;
        }
        const user = (dbgUser?.value||'debug').trim() || 'debug';
        await autoRunWithAnswers(answersMap, user);
        return;
      }
      toast('Debug JSON is invalid. Starting normal session.');
    }
    startSession(selTree.value);
  });

  btnRenderFinishPayload?.addEventListener('click', ()=>{
    const raw = dbgText?.value?.trim();
    if (!raw){
      return toast('Paste a JSON payload first.');
    }
    const json = parseJsonSafe(raw);
    if (!json){
      return toast('Invalid JSON payload.');
    }
    renderFinish(json);
  });

  btnStartTest?.addEventListener('click', async ()=>{
    if (!selTree.value){
      return toast('Select a tree first');
    }
    const raw = dbgText?.value?.trim();
    let answersMap = {};
    if (raw){
      const parsed = parseJsonSafe(raw);
      if (!parsed){
        return toast('Invalid JSON in Debug answers/payload');
      }
      if (parsed && typeof parsed==='object' && parsed.answers && typeof parsed.answers==='object'){
        answersMap = parsed.answers;
      }else{
        answersMap = parsed;
      }
    }
    const user = (dbgUser?.value||'debug').trim() || 'debug';
    await autoRunWithAnswers(answersMap, user);
  });

  backToQ?.addEventListener('click', ()=> renderQuestions());

  btnFinish?.addEventListener('click', async ()=>{
    try{
      const res = await fetch(`/dt/profile/${SESSION_ID}`);
      const data = await res.json();
      renderFinish(data);
    }catch(e){
      toast('Failed to open review.');
    }
  });

  btnSubmit?.addEventListener('click', async ()=>{
    openReviewModal();
  });

  // ----- Init -----
  (async ()=>{ await fetchTrees(); })();
  renderStart();

  // ---------- Skipped node registry logic ----------

  function calculateSkipped(previousId, currentId, allQuestions) {
    const adj = buildAdjacency(allQuestions);
    const restored = cleanupRegistryIfCurrentInside(currentId);
    if (restored){
      return formatRegistry();
    }
    const maxDepth = Object.keys(allQuestions).length + 5;
    const paths = findAllPaths(adj, previousId, currentId, maxDepth);

    if (!paths.length) {
      return formatRegistry();
    }

    let skipped = [];

    if (paths.length === 1) {
      const path = paths[0];
      if (path.length > 2) {
        skipped = path.slice(1, -1);
      }
    } else {
      paths.sort((a, b) => a.length - b.length);
      const shortest = paths[0];
      const longest  = paths[paths.length - 1];

      const internalShort = new Set(shortest.slice(1, -1));
      const internalLong  = longest.slice(1, -1);

      skipped = internalLong.filter(id => !internalShort.has(id));
    }

    if (skipped.length > 0) {
      skippedRegistry[previousId] = skipped;
    }

    return formatRegistry();
  }

  function buildAdjacency(allQuestions) {
    const adj = {};
    for (const id in allQuestions) {
      adj[id] = [];
    }

    for (const id in allQuestions) {
      const q = allQuestions[id];
      const nxt = q.next;

      if (typeof nxt === "string") {
        if (adj.hasOwnProperty(nxt)) {
          adj[id].push(nxt);
        }
      } else if (Array.isArray(nxt)) {
        nxt.forEach(item => {
          const gotoId = item.goto;
          if (gotoId && adj.hasOwnProperty(gotoId)) {
            adj[id].push(gotoId);
          }
        });
      }
    }

    return adj;
  }

  function findAllPaths(adj, start, goal, maxDepth) {
    const paths = [];

    function dfs(node, path) {
      if (path.length > maxDepth) return;
      if (node === goal) {
        paths.push(path.slice());
        return;
      }

      const neighbors = adj[node] || [];
      for (const next of neighbors) {
        if (path.includes(next)) continue;
        path.push(next);
        dfs(next, path);
        path.pop();
      }
    }

    if (!adj.hasOwnProperty(start) || !adj.hasOwnProperty(goal)) {
      return [];
    }

    dfs(start, [start]);
    return paths;
  }

  function cleanupRegistryIfCurrentInside(currentId) {
    for (const branch in skippedRegistry) {
      if (skippedRegistry[branch].includes(currentId)) {
        NODE_COUNT = NODE_COUNT + skippedRegistry[branch].length;
        delete skippedRegistry[branch];
        return true;
      }
      return false;
    }
  }

  function formatRegistry() {
    const out = {};
    for (const branch in skippedRegistry) {
      out[branch] = skippedRegistry[branch].length;
    }
    return out;
  }

})();