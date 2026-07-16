const views = [...document.querySelectorAll('.view')]
const navItems = [...document.querySelectorAll('.nav-item')]
function showView(id){
  views.forEach(v=>v.classList.toggle('active-view', v.id===id))
  navItems.forEach(n=>n.classList.toggle('active', n.dataset.view===id))
  document.querySelector('main').focus()
}
navItems.forEach(item=>item.addEventListener('click',()=>showView(item.dataset.view)))
document.querySelectorAll('[data-view-link]').forEach(btn=>btn.addEventListener('click',()=>showView(btn.dataset.viewLink)))
const dialog=document.getElementById('progressDialog')
document.getElementById('progressBtn').addEventListener('click',()=>dialog.showModal())
document.getElementById('closeDialog').addEventListener('click',()=>dialog.close())
dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()})
