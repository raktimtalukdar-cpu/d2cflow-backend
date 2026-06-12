export const ORDERS = [
  { id: 'ORD-9959102', channel: 'amazon', status: 'packed', payment: 'prepaid', customer: 'Priya Sharma', phone: '9876543210', city: 'Mumbai', pincode: '400001', state: 'MH', items: [{ name: 'Handcrafted Brass Diya Set', sku: 'DIYA-001', ean: '8901234567890', qty: 2, price: 1299 }, { name: 'Marble Incense Holder', sku: 'INC-003', ean: '8901234567891', qty: 1, price: 799 }], total: 3397, courier: 'Delhivery', awb: 'DEL1234567890', date: '2025-06-10', fulfillment: 'Amazon MCF' },
  { id: 'ORD-9959009', channel: 'flipkart', status: 'new', payment: 'cod', customer: 'Rahul Verma', phone: '8765432109', city: 'Delhi', pincode: '110001', state: 'DL', items: [{ name: 'Organic Ashwagandha Capsules 60ct', sku: 'ASHW-60', ean: '8902345678901', qty: 1, price: 649 }], total: 649, courier: null, awb: null, date: '2025-06-11', fulfillment: null },
  { id: 'ORD-9958484', channel: 'shopify', status: 'rtd', payment: 'prepaid', customer: 'Anjali Patel', phone: '7654321098', city: 'Ahmedabad', pincode: '380001', state: 'GJ', items: [{ name: 'Pure Cotton Kurta Set - Royal Blue', sku: 'KRT-RB-M', ean: '8903456789012', qty: 1, price: 2199 }], total: 2199, courier: 'Shiprocket', awb: 'SR9876543210', date: '2025-06-10', fulfillment: 'Shopify' },
  { id: 'ORD-9945508', channel: 'meesho', status: 'shipped', payment: 'cod', customer: 'Suresh Kumar', phone: '6543210987', city: 'Chennai', pincode: '600001', state: 'TN', items: [{ name: 'Steel Kadai 3L Non-Stick', sku: 'KAD-3L', ean: '8904567890123', qty: 1, price: 899 }], total: 899, courier: 'Ecom Express', awb: 'EX1234509876', date: '2025-06-09', fulfillment: null },
  { id: 'ORD-9935558', channel: 'amazon', status: 'delivered', payment: 'prepaid', customer: 'Deepa Nair', phone: '9432109876', city: 'Kochi', pincode: '682001', state: 'KL', items: [{ name: 'Bamboo Yoga Mat 6mm', sku: 'YOGA-BAM-6', ean: '8905678901234', qty: 1, price: 1599 }, { name: 'Yoga Block Set', sku: 'YOGA-BLK', ean: '8905678901235', qty: 1, price: 499 }], total: 2098, courier: 'BlueDart', awb: 'BD0987654321', date: '2025-06-08', fulfillment: 'Amazon MCF' },
  { id: 'ORD-9935593', channel: 'myntra', status: 'shipped', payment: 'prepaid', customer: 'Vikram Singh', phone: '8321098765', city: 'Jaipur', pincode: '302001', state: 'RJ', items: [{ name: 'Jaipuri Block Print Kurta', sku: 'KURTA-JP-L', ean: '8906789012345', qty: 1, price: 1799 }], total: 1799, courier: 'Xpressbees', awb: 'XB2345678901', date: '2025-06-09', fulfillment: null },
  { id: 'ORD-9935582', channel: 'shopify', status: 'rto', payment: 'cod', customer: 'Ramesh Gupta', phone: '7210987654', city: 'Patna', pincode: '800001', state: 'BR', items: [{ name: 'Ayurvedic Face Wash 200ml', sku: 'FW-AYU-200', ean: '8907890123456', qty: 2, price: 399 }], total: 798, courier: 'DTDC', awb: 'DT3456789012', date: '2025-06-07', fulfillment: null },
  { id: 'ORD-9926391', channel: 'amazon', status: 'packed', payment: 'prepaid', customer: 'Sneha Joshi', phone: '9109876543', city: 'Pune', pincode: '411001', state: 'MH', items: [{ name: 'Copper Water Bottle 1L', sku: 'COP-BOT-1L', ean: '8908901234567', qty: 3, price: 649 }], total: 1947, courier: 'Delhivery', awb: null, date: '2025-06-11', fulfillment: 'Amazon MCF' },
  { id: 'ORD-9926228', channel: 'flipkart', status: 'new', payment: 'cod', customer: 'Arjun Mehta', phone: '8098765432', city: 'Surat', pincode: '395001', state: 'GJ', items: [{ name: 'Terracotta Pot Set (Set of 3)', sku: 'TERRA-S3', ean: '8909012345678', qty: 1, price: 1199 }], total: 1199, courier: null, awb: null, date: '2025-06-12', fulfillment: null },
  { id: 'ORD-9918774', channel: 'meesho', status: 'new', payment: 'cod', customer: 'Pooja Reddy', phone: '7987654321', city: 'Hyderabad', pincode: '500001', state: 'TS', items: [{ name: 'Silk Saree - Kanjivaram', sku: 'SAREE-KANJ-RED', ean: '8910123456789', qty: 1, price: 4999 }], total: 4999, courier: null, awb: null, date: '2025-06-12', fulfillment: null },
  { id: 'ORD-9912345', channel: 'shopify', status: 'rtd', payment: 'prepaid', customer: 'Karthik Iyer', phone: '9876501234', city: 'Bengaluru', pincode: '560001', state: 'KA', items: [{ name: 'Neem Wood Comb Set', sku: 'COMB-NEEM', ean: '8901122334455', qty: 2, price: 299 }], total: 598, courier: 'Shadowfax', awb: null, date: '2025-06-11', fulfillment: null },
  { id: 'ORD-9908876', channel: 'amazon', status: 'cancelled', payment: 'prepaid', customer: 'Meera Pillai', phone: '8765012345', city: 'Thiruvananthapuram', pincode: '695001', state: 'KL', items: [{ name: 'Coconut Shell Bowls Set of 4', sku: 'CSB-4', ean: '8901233445566', qty: 1, price: 849 }], total: 849, courier: null, awb: null, date: '2025-06-08', fulfillment: null },
];

export const PRODUCTS = [
  { id: 9135886, name: 'Handcrafted Brass Diya Set', sku: 'DIYA-001', ean: '8901234567890', asin: 'B09XYZABC1', stock: { default: 520, tiruppur: 10, ludhiana: 10, delhi: 0 }, price: 1299, mrp: 1599, cost: 620, category: 'Home Decor', weight: 0.45, brand: 'ArtisanIndia', gst: 12 },
  { id: 9135887, name: 'Organic Ashwagandha Capsules 60ct', sku: 'ASHW-60', ean: '8902345678901', asin: 'B09XYZABC2', stock: { default: 280, tiruppur: 0, ludhiana: 50, delhi: 30 }, price: 649, mrp: 799, cost: 180, category: 'Health & Wellness', weight: 0.12, brand: 'PureHerbs', gst: 5 },
  { id: 9135888, name: 'Pure Cotton Kurta Set - Royal Blue M', sku: 'KRT-RB-M', ean: '8903456789012', asin: 'B09XYZABC3', stock: { default: 45, tiruppur: 120, ludhiana: 0, delhi: 20 }, price: 2199, mrp: 2799, cost: 780, category: 'Apparel', weight: 0.38, brand: 'WeaveIndia', gst: 12 },
  { id: 9135889, name: 'Bamboo Yoga Mat 6mm', sku: 'YOGA-BAM-6', ean: '8905678901234', asin: 'B09XYZABC4', stock: { default: 95, tiruppur: 0, ludhiana: 30, delhi: 15 }, price: 1599, mrp: 1999, cost: 550, category: 'Sports & Fitness', weight: 1.2, brand: 'ZenFlow', gst: 18 },
  { id: 9135890, name: 'Copper Water Bottle 1L', sku: 'COP-BOT-1L', ean: '8908901234567', asin: 'B09XYZABC5', stock: { default: 380, tiruppur: 40, ludhiana: 60, delhi: 25 }, price: 649, mrp: 899, cost: 220, category: 'Kitchen & Dining', weight: 0.35, brand: 'CopperCraft', gst: 12 },
  { id: 9135891, name: 'Silk Saree - Kanjivaram Red', sku: 'SAREE-KANJ-RED', ean: '8910123456789', asin: 'B09XYZABC6', stock: { default: 12, tiruppur: 8, ludhiana: 0, delhi: 5 }, price: 4999, mrp: 6499, cost: 2200, category: 'Apparel', weight: 0.65, brand: 'SilkRoute', gst: 5 },
  { id: 9135892, name: 'Terracotta Pot Set (Set of 3)', sku: 'TERRA-S3', ean: '8909012345678', asin: 'B09XYZABC7', stock: { default: 65, tiruppur: 0, ludhiana: 0, delhi: 10 }, price: 1199, mrp: 1499, cost: 380, category: 'Home Decor', weight: 1.8, brand: 'EarthWorks', gst: 12 },
  { id: 9135893, name: 'Neem Wood Comb Set', sku: 'COMB-NEEM', ean: '8901122334455', asin: 'B09XYZABC8', stock: { default: 440, tiruppur: 0, ludhiana: 80, delhi: 50 }, price: 299, mrp: 399, cost: 90, category: 'Personal Care', weight: 0.08, brand: 'NaturalKing', gst: 18 },
];

export const AUTOMATIONS = [
  {
    group: 'New Order',
    rules: [
      { id: 1, trigger: 'Order confirmed', conditions: [{ field: 'Payment type', op: 'is', value: 'COD' }], actions: ['Send WhatsApp confirmation', 'Change status → Pending COD confirm'], active: true },
      { id: 2, trigger: 'New order', conditions: [{ field: 'Source', op: 'is', value: 'Any shop' }], actions: ['Issue GST invoice', 'Send order confirmation email'], active: true },
    ]
  },
  {
    group: 'Ordering a Package',
    rules: [
      { id: 3, trigger: 'Order status changed to RTD', conditions: [], actions: ['Create Shiprocket shipment', 'Print label on printer', 'Update marketplace status'], active: true },
      { id: 4, trigger: 'Order status changed to RTD', conditions: [{ field: 'Source', op: 'is', value: 'Flipkart' }], actions: ['Push AWB to Flipkart', 'Send dispatch notification WhatsApp'], active: false },
    ]
  },
  {
    group: 'Package Tracking',
    rules: [
      { id: 5, trigger: 'Shipment delivered', conditions: [], actions: ['Change status → Delivered', 'Send delivery confirmation WhatsApp', 'Request review email'], active: true },
      { id: 6, trigger: 'NDR received', conditions: [], actions: ['Send NDR WhatsApp to customer', 'Alert founder on WhatsApp', 'Schedule reattempt'], active: true },
    ]
  },
  {
    group: 'RTO & Returns',
    rules: [
      { id: 7, trigger: 'RTO initiated', conditions: [{ field: 'Payment type', op: 'is', value: 'COD' }], actions: ['Restore inventory', 'Log RTO event', 'Alert founder'], active: true },
    ]
  },
];

export const RETURNS = [
  { id: 'RET-8047237', orderId: 'ORD-9935582', channel: 'amazon', status: 'new', customer: 'Ramesh Gupta', email: 'ramesh@gmail.com', phone: '+919876543210', reason: 'Product not as described', amount: 798, items: [{ name: 'Ayurvedic Face Wash 200ml', sku: 'FW-AYU-200', qty: 2, price: 399 }], date: '2025-06-11' },
  { id: 'RET-8047190', orderId: 'ORD-9908876', channel: 'flipkart', status: 'in_progress', customer: 'Meera Pillai', email: 'meera@gmail.com', phone: '+918901234567', reason: 'Damaged in transit', amount: 849, items: [{ name: 'Coconut Shell Bowls Set of 4', sku: 'CSB-4', qty: 1, price: 849 }], date: '2025-06-09' },
  { id: 'RET-8047001', orderId: 'ORD-9908000', channel: 'amazon', status: 'completed', customer: 'Anita Desai', email: 'anita@gmail.com', phone: '+917654321890', reason: 'Wrong size delivered', amount: 2199, items: [{ name: 'Pure Cotton Kurta Set', sku: 'KRT-RB-L', qty: 1, price: 2199 }], date: '2025-06-07' },
  { id: 'RET-8046890', orderId: 'ORD-9905600', channel: 'shopify', status: 'rto', customer: 'Manoj Tiwari', email: 'manoj@gmail.com', phone: '+919012345678', reason: 'Customer refused delivery', amount: 1299, items: [{ name: 'Handcrafted Brass Diya Set', sku: 'DIYA-001', qty: 1, price: 1299 }], date: '2025-06-06' },
];

export const CHANNEL_STATS = {
  amazon: { new: 3, rtd: 2, shipped: 5, delivered: 28 },
  flipkart: { new: 2, rtd: 1, shipped: 3, delivered: 15 },
  meesho: { new: 4, rtd: 0, shipped: 2, delivered: 8 },
  myntra: { new: 1, rtd: 1, shipped: 2, delivered: 6 },
  shopify: { new: 5, rtd: 3, shipped: 4, delivered: 19 },
};

export const TRIGGER_OPTIONS = [
  'New order', 'Order confirmed', 'Order status changed', 'Payment received',
  'Order status changed to RTD', 'Shipment created', 'Shipment picked up',
  'Shipment delivered', 'NDR received', 'RTO initiated', 'Return requested',
  'Product stock below threshold', 'Product stock above threshold',
  'COD confirmation received', 'COD confirmation rejected',
];

export const ACTION_OPTIONS = [
  'Send WhatsApp message', 'Send email', 'Issue GST invoice',
  'Change order status', 'Create Shiprocket shipment', 'Print label',
  'Push AWB to marketplace', 'Restore inventory', 'Create purchase order',
  'Alert founder on WhatsApp', 'Add order tag', 'Schedule reattempt',
  'Send dispatch notification', 'Request review email', 'Log event',
];

export const CONDITION_FIELDS = [
  'Source', 'Payment type', 'Order status', 'Channel', 'Product tag',
  'Courier', 'Pincode', 'State', 'Order total', 'SKU contains',
];
