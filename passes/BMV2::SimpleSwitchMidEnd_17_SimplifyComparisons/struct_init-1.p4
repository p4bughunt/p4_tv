--- before_pass
+++ after_pass
@@ -11,11 +11,11 @@ control I(inout metadata_t meta) {
     H h_0;
     apply {
         h_0.setValid();
-        if (meta.foo == PortId_t {_v = 9w192}) {
+        if (true && meta.foo._v == 9w192) {
             meta.foo._v = meta.foo._v + 9w1;
             h_0.setValid();
             h_0 = H {b = 32w2};
-            if (h_0 == H {b = 32w1}) 
+            if (!h_0.isValid() && !true || h_0.isValid() && true && h_0.b == 32w1) 
                 h_0.setValid();
         }
     }