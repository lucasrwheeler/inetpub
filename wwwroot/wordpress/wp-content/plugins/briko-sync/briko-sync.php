<?php
/**
 * Plugin Name: Brikō Sync
 * Description: Sync products from the Brikō API into WooCommerce and forward WooCommerce orders to the Brikō backend.
 * Version: 1.0
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'BRIKO_API_BASE', 'http://10.0.0.10:8000' );


// ------------------------------------------------------------
// ADMIN PAGE (Manual Product Sync)
// ------------------------------------------------------------
add_action( 'admin_menu', function () {
    add_menu_page(
        'Brikō Sync',
        'Brikō Sync',
        'manage_woocommerce',
        'briko-sync',
        'briko_sync_page'
    );
});

function briko_sync_page() {
    if ( isset( $_POST['briko_sync_now'] ) ) {
        briko_run_product_sync();
        echo '<div class="updated"><p>Brikō product sync completed.</p></div>';
    }

    echo '<div class="wrap"><h1>Brikō Sync</h1>';
    echo '<form method="post">';
    echo '<p><button class="button button-primary" name="briko_sync_now" value="1">Sync Products Now</button></p>';
    echo '</form></div>';
}


// ------------------------------------------------------------
// PRODUCT SYNC (Brikō → WooCommerce)
// ------------------------------------------------------------
function briko_run_product_sync() {
    $response = wp_remote_get( BRIKO_API_BASE . '/sync/products' );

    if ( is_wp_error( $response ) ) {
        error_log("Brikō Sync Error: " . $response->get_error_message());
        return;
    }

    $body = wp_remote_retrieve_body( $response );
    $products = json_decode( $body, true );

    if ( ! is_array( $products ) ) {
        error_log("Brikō Sync Error: Invalid product JSON");
        return;
    }

    foreach ( $products as $p ) {
        $sku = $p['sku'];

        // Find existing product by SKU
        $existing_id = wc_get_product_id_by_sku( $sku );

        if ( $existing_id ) {
            $product = new WC_Product_Simple( $existing_id );
        } else {
            $product = new WC_Product_Simple();
        }

        $product->set_name( $p['name'] );
        $product->set_regular_price( $p['regular_price'] );
        $product->set_description( $p['description'] );
        $product->set_sku( $sku );
        $product->set_manage_stock( true );
        $product->set_stock_quantity( intval( $p['stock_quantity'] ) );
        $product->save();
    }
}


// ------------------------------------------------------------
// ORDER SYNC (WooCommerce → Brikō)
// ------------------------------------------------------------
// This registers the endpoint: /wc-api/briko_order_webhook
add_action('woocommerce_api_briko_order_webhook', 'briko_forward_order_to_api');

function briko_forward_order_to_api() {

    // Safety check
    if ( ! isset($_GET['order_id']) ) {
        status_header(400);
        echo "Missing order_id";
        exit;
    }

    $order_id = intval($_GET['order_id']);
    $order = wc_get_order($order_id);

    if ( ! $order ) {
        status_header(404);
        echo "Order not found";
        exit;
    }

    // Build payload
    $payload = $order->get_data();

    $payload['line_items'] = array_map(function($item) {
        return [
            'product_id' => $item->get_product_id(),
            'quantity'   => $item->get_quantity(),
            'price'      => $item->get_total()
        ];
    }, $order->get_items());

    // Send to FastAPI
    wp_remote_post(BRIKO_API_BASE . '/sync/orders/from-woocommerce', [
        'method'  => 'POST',
        'headers' => ['Content-Type' => 'application/json'],
        'body'    => json_encode($payload)
    ]);

    status_header(200);
    echo "OK";
    exit;
}




