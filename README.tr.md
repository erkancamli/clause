# Clause

## Clause nedir?

Clause, ölçülebilen olaylara bağlı sigorta teminatlarının fiyatlanması, düzenlenmesi ve ödeme sürecini Rialo mimarisiyle modelleyen bir protokoldür. Bu sürümde deprem, kuraklık, araç için sel, konut için fırtına ve uçuş gecikmesi teminatları bulunur.

Clause bir sigorta şirketi değildir. Ruhsatlı şirketlerin kaydını, fiyatlama motorunu, sermaye havuzunu ve poliçe koşullarına göre işleyen ödeme altyapısını sağlar. Gerçek hasarı ekspertizle belirlemez; ödeme, poliçede önceden kararlaştırılan ölçüme bağlıdır.

## Parametrik teminat nasıl çalışır?

1. Korunacak varlık veya uçuş, teminat tutarı, süre ve ölçülecek olay belirlenir. Ölçüm kaynağı, eşik ve hesaplama kuralları poliçede yer alır.
2. Poliçenin aboneliği ilgili ölçümü izler. Doğrulayıcıların bildirdiği değerler, poliçenin uzlaşma kurallarına göre değerlendirilir.
3. Kabul edilen ölçüm eşiği karşıladığında, diğer poliçe ve uygunluk koşulları da sağlanıyorsa ödeme aynı blokta yürütülür. Ayrıca hasar ihbarı veya eksper kararı beklenmez.

Örneğin deprem teminatında poliçeye göre sigortalı adresteki sarsıntı şiddeti ya da belirli bir yarıçap içindeki en büyük deprem büyüklüğü esas alınabilir. Hasar oluşması tek başına ödeme anlamına gelmez: ölçüm poliçedeki eşiğe ulaşmazsa ödeme yapılmaz.

Bu sürümde zincir ve teminatı sonuçlandıran veri kaynakları simüle edilir; ölçümler canlı API yerine tehlike modellerinden üretilir. Fiyatlama, sermaye hesabı ve uygunluk kontrolleri kodda uygulanır; model parametreleri örnek niteliğindedir. Yerel demo, gerçek sigorta veya gerçek para ödemesi değildir. Teknik ayrıntılar için [ana README](README.md) dosyasına bakın.

## Poliçeyi kim düzenler, ödeme kaynağı nedir?

Poliçeyi, alıcının ülkesinde ve ilgili risk için yetkili, ruhsatlı bir sigorta şirketi düzenler. Şirket kaydolduktan sonra operatör ruhsatını ilgili düzenleyici kurumun kayıtlarından kontrol eder. Kaydı bulunmayan veya yetkisi uygun olmayan bir şirket teminat düzenleyemez.

Siteden yapılan başvuru ayrıca sigorta şirketinin incelemesine gider. Şirket gerekli kontrolleri tamamlayıp onayladığında poliçe düzenlenir. Başvuru sırasında bekletilen tutar, ret halinde iade edilir.

Ödemelerin arkasında, risk üstlenmek isteyen sermaye sağlayıcılarının katkıda bulunduğu bir havuz vardır. Primler havuzun zarar ve sermaye karşılıklarını besler. Sermaye yeterliliği ve risk yoğunlaşması sınırları, havuzun taşıyamayacağı yeni teminatları engeller; aktif poliçelere karşılık ayrılan sermaye serbestçe çekilemez.

Yeni bir kurulumda şirket kaydı boştur. Demo şirketleri yalnızca gösterim için kullanılan örneklerdir; gerçek şirket veya ruhsat olarak değerlendirilmemelidir.

## Yerelde çalıştırma

Python 3.10 veya üzeri gerekir. Depoyu indirin ve klasörüne geçin:

```bash
git clone https://github.com/erkancamli/clause.git
cd clause
```

Ana README ile aynı kurulum ve başlatma komutlarını kullanın:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CLAUSE_FAUCET=1 python -m clause serve --port 8080
```

Tarayıcıda http://127.0.0.1:8080 adresini açın ve dili Türkçe seçin. Önce ana sayfayı inceleyin, ardından bir teminat teklifi oluşturun. Kanıt bölümünden sonuçlanan poliçelerin kayıtlarını inceleyebilirsiniz. `CLAUSE_FAUCET=1`, yerel gösterimde kullanılacak deneme bakiyesi özelliğini açar.

## Canlı site

[clause.insure](https://clause.insure)

Canlı sitede görünen demo ve ağ açıklamalarını dikkate alın; sitenin erişilebilir olması gerçek sigorta teminatı sunulduğu anlamına gelmez.

Lisans ve kullanım koşulları için [LICENSE](LICENSE) dosyasına bakın.
