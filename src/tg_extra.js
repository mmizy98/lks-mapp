<script>
/* Telegram Mini App glue: theme, full height, no swipe-to-close while panning the map, deep links (?startapp=403). */
(function(){
  var tg=window.Telegram&&window.Telegram.WebApp; if(!tg||!tg.initData&&!tg.platform) return;
  try{tg.ready(); tg.expand()}catch(e){}
  try{tg.setHeaderColor('#0a52ad'); tg.setBackgroundColor('#000000'); if(tg.setBottomBarColor) tg.setBottomBarColor('#0d0d0f')}catch(e){}
  try{if(tg.disableVerticalSwipes) tg.disableVerticalSwipes()}catch(e){}
  document.documentElement.classList.add('in-tg');
  var sp=(tg.initDataUnsafe&&tg.initDataUnsafe.start_param)||'';
  if(sp&&window.ULK_OPEN){ // "403", "312a", "from_1101__to_403"
    var m=sp.match(/^from_(.+)__to_(.+)$/); setTimeout(function(){ m?window.ULK_OPEN(m[2],m[1]):window.ULK_OPEN(sp) },50);
  }
  window.ULK_HAPTIC=function(){try{tg.HapticFeedback.notificationOccurred('success')}catch(e){}};
})();
</script>
