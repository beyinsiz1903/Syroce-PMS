const DEFAULT_CONTRACT = {
  dataSource: 'PMS işlem kayıtları',
  dateScope: 'Ekranda seçilen rapor dönemi',
  financialScope: 'Rapor türüne göre tahakkuk, folyo hareketi veya tahsilat',
  currencyRule: 'Farklı para birimleri dönüştürülmeden toplanmaz; ayrı gösterilir.',
};

const FINANCIAL_CONTRACT = {
  ...DEFAULT_CONTRACT,
  dataSource: 'Onaylı folyo hareketleri, rezervasyon gece kayıtları ve ödeme kayıtları',
  financialScope: 'Tahsilat, oda geliri ve fiyat düzeltmesi ayrı kalemlerdir.',
};

const COLLECTION_CURRENCY_RULE = 'TRY raporlama toplamı işlemde saklanan tarihsel kurla hesaplanır; kuru eksik hareketler uyarıyla ayrılır. Fiziken alınan döviz ayrıca gösterilir.';
const GL_CURRENCY_RULE = 'Genel muhasebe TRY baz defteridir. Yabancı para bilgisi ayrı tutulur; tesis döviziyle yeniden etiketlenmez.';

export const REPORT_CONTRACTS = {
  flash_report: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili PMS iş günü; oda durumu güncel operasyon anıdır.' },
  overview: { ...FINANCIAL_CONTRACT, dateScope: 'Seçilen gün veya son 30 gün' },
  revenue: { ...FINANCIAL_CONTRACT, financialScope: 'Gelir; tahsilat yerine geçmez. İptal ve fiyat düzeltmeleri ayrı gösterilir.' },
  adr_revpar: {
    ...FINANCIAL_CONTRACT,
    financialScope: 'ADR = oda geliri / satılan oda-gecesi. RevPAR = oda geliri / satılabilir oda-gecesi.',
  },
  occupancy: { ...DEFAULT_CONTRACT, dataSource: 'Satılabilir oda envanteri ve konaklama gece kayıtları', financialScope: 'Finansal tutar içermez.' },
  forecast_reports: { ...FINANCIAL_CONTRACT, dataSource: 'Mevcut rezervasyonlar ve tarihsel konaklama geceleri', dateScope: 'Bu raporun içindeki ufuk, hedef tarih ve kazanım dönemi seçimleri', financialScope: 'Tahmin, kesinleşmiş gelir veya tahsilat değildir.' },
  period: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili dönem, önceki eş uzunluklu dönem ve 365 gün önceki karşılaştırma' },
  room_types: { ...FINANCIAL_CONTRACT, dateScope: 'Doluluk seçili güne, gelir seçili rapor dönemine aittir.', dataSource: 'Aktif oda tipleri, satışa kapalı oda aralıkları ve işlenmiş gelir kayıtları' },
  guests: { ...DEFAULT_CONTRACT, dataSource: 'Seçili dönemin rezervasyon ve ek misafir kayıtları', financialScope: 'Konaklama toplamı rezervasyonda bir kez gösterilir; tahsilat değildir.' },
  inhouse: { ...DEFAULT_CONTRACT, dateScope: 'Seçili tarihte fiilen konaklayanlar; çıkış günü dahil değildir.', dataSource: 'Rezervasyon gece aralıkları, birincil ve ek misafirler', financialScope: 'Gece fiyatı konaklamaya aittir; her misafire yeniden yazılmaz.' },
  nationality: { ...DEFAULT_CONTRACT, dataSource: 'Seçili dönem misafir listesi; ek misafirler dahildir.', financialScope: 'Kişi dağılımıdır; rezervasyon veya gelir dağılımı değildir.' },
  front_office: { ...DEFAULT_CONTRACT, dateScope: 'Seçili gündeki beklenen giriş ve çıkışlar', dataSource: 'Rezervasyon ve misafir kayıtları', financialScope: 'Konaklama fiyatı tahsilat anlamına gelmez.' },
  noshow: { ...DEFAULT_CONTRACT, dateScope: 'No-show giriş tarihine; iptal, iptal hareketinin tarihine aittir.', dataSource: 'Seçili dönem no-show ve iptal rezervasyonları', financialScope: 'Rezervasyon bedeli otomatik olarak gerçekleşmiş zarar veya tahsilat sayılmaz.' },
  room_status: { ...DEFAULT_CONTRACT, dataSource: 'Aktif odaların güncel operasyon durumları', dateScope: 'Güncel anlık durum; geçmiş tarihli oda fotoğrafı değildir.', financialScope: 'Finansal tutar içermez.' },
  housekeeping: { ...DEFAULT_CONTRACT, dataSource: 'Kat hizmetleri görevleri ve odaların güncel temizlik durumları', dateScope: 'Görev/hareketler seçili güne; oda durumu güncel ana aittir.', financialScope: 'Finansal tutar içermez.' },
  channels: { ...FINANCIAL_CONTRACT, dataSource: 'Rezervasyon kanalları ve rezervasyonla eşleştirilmiş işlenmiş gelirler', dateScope: 'Seçili gün veya son 30 gün; gelir ve rezervasyon sayısı ayrı ölçülerdir.' },
  sources: { ...FINANCIAL_CONTRACT, dataSource: 'Rezervasyon kaynakları ve rezervasyonla eşleştirilmiş işlenmiş gelirler', dateScope: 'Seçili gün veya son 30 gün; gelir ve rezervasyon sayısı ayrı ölçülerdir.' },
  payments: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili iş günü', financialScope: 'Yalnızca geçerli tahsilat ve iade hareketleri; fiyat düzeltmeleri hariçtir.', currencyRule: COLLECTION_CURRENCY_RULE },
  front_cashier: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili iş günü', financialScope: 'Folyo hareketleri ve geçerli tahsilatlar ayrı hesaplanır.', currencyRule: COLLECTION_CURRENCY_RULE },
  cash_movements: { ...FINANCIAL_CONTRACT, dateScope: 'Hareketin fiilen işlendiği seçili takvim günü; PMS iş gününden farklı olabilir.', financialScope: 'Yalnızca geçerli tahsilat ve iade hareketleri.', currencyRule: COLLECTION_CURRENCY_RULE },
  rate_control: { ...DEFAULT_CONTRACT, dataSource: 'Rezervasyon gece fiyatları ve folyo oda tahakkukları', financialScope: 'Fiyat farkı tahsilat değildir; yalnızca mutabakat farkı olarak gösterilir.' },
  trial_balance: { ...FINANCIAL_CONTRACT, dataSource: 'Ortak gelir, ödeme, konaklama gecesi ve açık folyo defteri', dateScope: 'Gelir ve tahsilat seçili güne; açık folyo ve depozitolar güncel bakiyeye aittir.', financialScope: 'Operasyonel karşılaştırmadır; gelir-tahsilat farkı muhasebe fişi dengesizliği değildir.' },
  daily_analysis: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili PMS iş günü', financialScope: 'İşlenmiş oda geliri esas alınır; yalnız eksik gün/döviz için tahakkuk kullanılır.' },
  expenses: { ...DEFAULT_CONTRACT, dataSource: 'Muhasebe gider kayıtları', dateScope: 'Bu ekranın içindeki başlangıç/bitiş ve para birimi seçimi', financialScope: 'Giderler seçili dövizde gösterilir; ödeme veya GL gideriyle aynı kapsam olduğu varsayılmaz.' },
  departments: { ...DEFAULT_CONTRACT, dataSource: 'Kat hizmetleri, teknik servis ve fatura durumları', dateScope: 'Güncel açık kayıtlar ve seçili dönem tamamlanan hareketler ayrı gösterilir.', financialScope: 'Fatura/görev adetleridir; parasal toplam değildir.' },
  fnb: { ...FINANCIAL_CONTRACT, dataSource: 'İşlenmiş F&B folyo/ek gelir ve tamamlanmış POS kayıtları', dateScope: 'Seçili gün', financialScope: 'İadeler işaretli, odaya aktarımlar tek kayıt; bahşiş gelirden ayrıdır.' },
  gl_trial_balance: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', dateScope: 'Seçili tarihe kadar birikimli', financialScope: 'Muhasebeleşmiş borç ve alacak bakiyeleri.', currencyRule: GL_CURRENCY_RULE },
  income_statement: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', financialScope: 'Muhasebeleşmiş gelir, gider ve dönem sonucu.', currencyRule: GL_CURRENCY_RULE },
  balance_sheet: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', dateScope: 'Seçili tarih itibarıyla birikimli', financialScope: 'Rapor tarihi itibarıyla varlık, yükümlülük ve özkaynak.', currencyRule: GL_CURRENCY_RULE },
  journal: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', financialScope: 'Yevmiye hareketleri; taslak fişler hariçtir.', currencyRule: GL_CURRENCY_RULE },
  official: { ...DEFAULT_CONTRACT, dataSource: 'Seçili tarihteki misafir ve konaklama kayıtları', financialScope: 'Resmî liste; finansal toplamlar yalnızca bilgi amaçlıdır.' },
  police: { ...DEFAULT_CONTRACT, dataSource: 'Seçili tarihte fiilen konaklayan misafir kayıtları', financialScope: 'Finansal tutar içermez.' },
};

export function getReportContract(section) {
  return REPORT_CONTRACTS[section] || DEFAULT_CONTRACT;
}
